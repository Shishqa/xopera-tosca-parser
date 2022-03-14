from opera_tosca_parser.parser.yaml.node import Node

from .attribute_definition import AttributeDefinition
from .property_definition import PropertyDefinition
from .range import Range
from ..entity import Entity
from ..list import List
from ..map import Map
from ..reference import Reference
from ..string import String


class CapabilityDefinition(Entity):
    ATTRS = dict(
        type=Reference("capability_types"),
        description=String,
        properties=Map(PropertyDefinition),
        attributes=Map(AttributeDefinition),
        valid_source_types=List(Reference("node_types")),
        occurrences=Range,
    )
    REQUIRED = {"type"}

    @classmethod
    def normalize(cls, yaml_node: Node) -> Node:
        """
        Normalize CapabilityDefinition object
        :param yaml_node: YAML node
        :return: Normalized Node object
        """
        if not isinstance(yaml_node.value, (str, dict)):
            cls.abort("Expected string or map.", yaml_node.loc)
        if isinstance(yaml_node.value, str):
            return Node({Node("type"): yaml_node})
        return yaml_node
