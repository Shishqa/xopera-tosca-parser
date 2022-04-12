import argparse
import typing
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
from zipfile import is_zipfile

import shtab
import yaml

from opera_tosca_parser.error import OperaToscaParserError, ParseError
from opera_tosca_parser.parser import tosca
from opera_tosca_parser.parser.tosca.csar import CloudServiceArchive, DirCloudServiceArchive
from opera_tosca_parser.template.topology import Topology


def add_parser(subparsers: argparse._SubParsersAction):
    """
    Adds a new parser to subparsers
    :param subparsers: Subparsers action
    """
    parser = subparsers.add_parser(
        "parse",
        help="Parse TOSCA YAML service template or TOSCA CSAR"
    )
    parser.add_argument(
        "--inputs", "-i", type=argparse.FileType("r"),
        help="YAML or JSON file with inputs",
    ).complete = shtab.FILE
    parser.add_argument(
        "csar_or_service_template", type=str, nargs="?",
        help="TOSCA YAML service template or uncompressed/compressed TOSCA CSAR"
    ).complete = shtab.FILE
    parser.set_defaults(func=_parser_callback)


def _parser_callback(args: argparse.Namespace) -> int:
    """
    Parser callback function
    :param args: Supplied arguments
    :return: Exit code - 0 if parsing successful or 1 if not
    """
    try:
        inputs = yaml.safe_load(args.inputs) if args.inputs else {}
    except yaml.YAMLError as e:
        print(f"Invalid inputs: {e}")
        return 1

    if args.csar_or_service_template is None:
        csar_or_st_path = PurePath(".")
    else:
        csar_or_st_path = PurePath(args.csar_or_service_template)

    try:
        print("Parsing TOSCA CSAR or service template...")
        parse(csar_or_st_path, inputs)
        print("Done.")
    except ParseError as e:
        print(f"{e.loc}: {e}")
        return 1
    except OperaToscaParserError as e:
        print(str(e))
        return 1

    return 0


def parse(csar_or_st_path: PurePath, inputs: typing.Optional[dict]) -> Topology:
    """
    Parse TOSCA CSAR or service template
    :param csar_or_st_path: Path to TOSCA CSAR or service template
    :param inputs: TOSCA inputs
    :return: Topology object representing TOSCA CSAR entrypoint or service template
    """
    if is_zipfile(csar_or_st_path) or Path(csar_or_st_path).is_dir():
        return parse_csar(csar_or_st_path, inputs)
    else:
        return parse_service_template(csar_or_st_path, inputs)


def parse_csar(csar_path: PurePath, inputs: typing.Optional[dict]) -> Topology:
    """
    Parse TOSCA CSAR
    :param csar_path: Path to TOSCA CSAR
    :param inputs: TOSCA inputs
    :return: Topology object representing TOSCA CSAR entrypoint
    """
    if inputs is None:
        inputs = {}

    csar = CloudServiceArchive.create(csar_path)
    csar.validate_csar()
    entrypoint = csar.get_entrypoint()

    if entrypoint is not None:
        if isinstance(csar, DirCloudServiceArchive):
            workdir = Path(csar_path)
            ast = tosca.load(workdir, entrypoint)
            return ast.get_template(inputs)
        else:
            with TemporaryDirectory() as csar_validation_dir:
                csar.unpackage_csar(csar_validation_dir)
                workdir = Path(csar_validation_dir)
                ast = tosca.load(workdir, entrypoint)
                return ast.get_template(inputs)


def parse_service_template(service_template_path: PurePath, inputs: typing.Optional[dict]) -> Topology:
    """
    Parse TOSCA service template
    :param service_template_path: Path to TOSCA service template
    :param inputs: TOSCA inputs
    :return: Topology object representing TOSCA service template
    """
    if inputs is None:
        inputs = {}
    workdir = Path(service_template_path.parent)
    ast = tosca.load(workdir, PurePath(service_template_path.name))
    return ast.get_template(inputs)
