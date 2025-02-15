from typing import Optional, Dict, Any, Tuple, List as TypingList

from opera_tosca_parser.parser.tosca.v_1_3.template.node import Node
from opera_tosca_parser.parser.tosca.v_1_3.template.operation import Operation
from opera_tosca_parser.parser.tosca.v_1_3.template.policy import Policy
from opera_tosca_parser.parser.tosca.v_1_3.template.trigger import Trigger
from opera_tosca_parser.parser.tosca.v_1_3.value import Value
from .collector_mixin import CollectorMixin  # type: ignore
from .policy_type import PolicyType
from .trigger_definition import TriggerDefinition
from ..list import List
from ..map import Map
from ..reference import Reference, ReferenceXOR
from ..string import String
from ..void import Void


class PolicyDefinition(CollectorMixin):
    ATTRS = dict(
        type=Reference("policy_types"),
        description=String,
        metadata=Map(String),
        properties=Map(Void),
        targets=List(ReferenceXOR(("topology_template", "node_templates"), ("topology_template", "groups"))),
        triggers=Map(TriggerDefinition),
    )
    REQUIRED = {"type"}

    def get_template(self, name: str, service_ast: Dict[str, Any], nodes: Dict[str, Node]) -> Policy:
        """
        Get Policy object from template
        :param name: Node name
        :param service_ast: Abstract syntax tree dict
        :param nodes: Node objects from TOSCA template
        :return: Policy object
        """
        # targets will be used also for collecting triggers so retrieve them here only once
        targets = self.collect_targets(service_ast)

        self.collected_properties = self.collect_properties(service_ast)

        policy = Policy(
            name=name,
            types=self.collect_types(service_ast),
            properties=self.collected_properties,
            targets=self.resolve_targets(targets, nodes),
            triggers=self.collect_triggers(service_ast, targets, nodes)
        )

        return policy

    # the next function is not part of the CollectorMixin because targets are policy only thing
    def collect_target_definitions(self, typ: PolicyType) -> Dict[str, Any]:
        """
        Collect TOSCA policy target definitions
        :param typ: PolicyType
        :return: Target definitions dict
        """
        return {target.data: target for target in typ.get("targets", {})}

    # the next function is not part of the CollectorMixin because targets are policy only thing
    def collect_targets(self, service_ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect TOSCA policy targets
        :param service_ast: Abstract syntax tree dict
        :return: Targets dict
        """
        typ = self.type.resolve_reference(service_ast)
        definitions = self.collect_target_definitions(typ)
        assignments = {target.data: target for target in self.get("targets", {})}
        if len(assignments) > 0:
            definitions = assignments
        # print('ASSIGNMENTS: ', definitions)

        # duplicate_targets = set(assignments.keys()).intersection(definitions.keys())
        # if duplicate_targets:
        #     for duplicate in duplicate_targets:
        #         definitions.pop(duplicate)

        # definitions.update(assignments)
        # print('DEFINITIONS: ', definitions)

        return {
            name: (assignments.get(name) or definition).resolve_reference(service_ast)
            for name, definition in definitions.items()
        }

    # the next function is not part of the CollectorMixin because targets are policy only thing
    def resolve_targets(self, targets: Dict[str, Any], nodes: Dict[str, Node]) -> Dict[str, Any]:
        """
        Resolve TOSCA policy targets (link targets to their corresponding node objects)
        :param targets: Targets dict
        :param nodes: Node objects from TOSCA template
        :return: Resolved targets dict
        """
        resolved_targets = {}
        if targets:
            for target_name in targets.keys():
                for node_name, node in nodes.items():
                    if node_name == target_name or node.types[0] == target_name:
                        # assign node object when target name is the same as the name of node object/template or
                        # when target name matches node object's type
                        resolved_targets[node_name] = node
        return resolved_targets

    # the next function is not part of the CollectorMixin because triggers are policy only thing
    def collect_trigger_definitions(self, typ: PolicyType, service_ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect TOSCA policy trigger definitions
        :param typ: PolicyType
        :param service_ast: Abstract syntax tree dict
        :return: Trigger definitions dict
        """
        return typ.collect_definitions("triggers", service_ast)

    # the next function is not part of the CollectorMixin because triggers are policy only thing
    def collect_trigger_action_from_interfaces(self, targeted_nodes: Dict[str, Node],
                                               call_operation_name: Optional[str],
                                               action: Dict[str, Any], inputs: Dict[str, Any]) -> Optional[Tuple[str, str, Operation]]:
        """
        Collect TOSCA policy trigger action from TOSCA interfaces
        :param targeted_nodes: Target Node objects from TOSCA template
        :param call_operation_name: Name from call_operation
        :param action: Action to retrieve
        :return: Tuple with collected action
        """
        collected_action = None
        actions_found = 0
        for _, target_node in targeted_nodes.items():
            # loop through interfaces from targeted nodes
            for interface_name, interface in target_node.interfaces.items():
                # loop through interface operations from targeted nodes
                for operation_name, operation in interface.operations.items():
                    # find the corresponding node's interface operation
                    if str(interface_name) + "." + str(operation_name) == str(call_operation_name):
                        actions_found += 1

                        # update the operation inputs with inputs from trigger's activity definition
                        extra_inputs = {
                            k: Value(None, True, Value(None, True, v).eval(self, k))
                            for k, v in inputs.items()
                        }
                        # print('EXTRA: ', extra_inputs)

                        collected_action = (interface_name, operation_name, operation, extra_inputs)
                        break

        if actions_found == 0:
            self.abort(
                f"Trigger action: {call_operation_name} from call_operation does not belong to any node interface. "
                f"Make sure that you have referenced it correctly (as <interface_sub_name>.<operation_sub_name>, where "
                f"interface_sub_name is the interface name and the operation_sub_name is the name of the operation "
                f"within this interface). The node that you're targeting with interface operation also has to be used "
                f"in topology_template/node_templates section", self.loc
            )
        # elif actions_found > 1:
        #     self.abort(
        #         f"Found duplicated trigger actions: {call_operation_name} from call_operation. It seems that the "
        #         f"operation with the same name belongs to two different node types/templates.", self.loc
        #     )

        return collected_action

    # the next function is not part of the CollectorMixin because triggers are policy only thing
    def collect_trigger_target_nodes(self, target_filter: Optional[Tuple[str, Any]], nodes: Dict[str, Node],
                                     policy_targets: Dict[str, Any]) -> Dict[str, Node]:
        """
        Collect TOSCA policy trigger action from TOSCA interfaces
        :param target_filter: Target filter
        :param nodes: Node objects from TOSCA template
        :param policy_targets: Policy targets
        :return: Target Node objects from TOSCA template for trigger
        """
        # pylint: disable=no-self-use
        targeted_nodes = {}
        if target_filter:
            # if target node filter is applied collect just one targeted node from it
            for node_name, node in nodes.items():
                if node_name == target_filter[0] or node.types[0] == target_filter[0]:
                    targeted_nodes[node_name] = node
                    break
        elif policy_targets:
            # if target_filter is not present collect target nodes from policy's targets
            for node_name, node in nodes.items():
                for policy_target_name, _ in policy_targets.items():
                    if policy_target_name in (node_name, node.types[0]):
                        targeted_nodes[node_name] = node
        else:
            # if we don't have any target node limits take all template's nodes into account
            targeted_nodes = nodes

        return targeted_nodes

    # the next function is not part of the CollectorMixin because triggers are policy only thing
    def collect_trigger_actions(self, definition: Dict[str, Any],
                                target_filter: Optional[Tuple[str, Any]], nodes: Dict[str, Node],
                                policy_targets: Dict[str, Any]) -> TypingList[Tuple[str, str, Operation]]:
        """
        Collect TOSCA policy trigger action from TOSCA interfaces
        :param definition: Trigger definition
        :param target_filter: Target filter
        :param nodes: Node objects from TOSCA template
        :param policy_targets: Policy targets
        :return: Trigger actions
        """
        actions = []
        action_definitions = definition.get("action", [])
        for action in action_definitions:
            # TODO: implement support for other types of trigger activity definitions.
            if list(action)[0] != "call_operation":
                self.abort(
                    f"Unsupported trigger activity definitions: {list(action)[0]}. Only call_operation is supported.",
                    self.loc
                )
            else:
                inputs = {}

                # collect connected node interface operations
                call_operation = action.get("call_operation", None)
                call_operation_name = None
                # handle short call_operation notation
                if isinstance(call_operation.data, str):
                    call_operation_name = call_operation.data
                # handle extended call_operation notation
                elif isinstance(call_operation.data, dict):
                    call_operation_name = call_operation.data.get("operation", None)
                    inputs = call_operation.data.get("inputs", None)
                else:
                    self.abort(
                        f"Invalid call operation activity definition type: {type(call_operation.data)}.", self.loc
                    )

                # having no operation name should never happen but to be completely sure we can also check here
                if not call_operation_name:
                    self.abort("Missing required name for call_operation activity definition.", self.loc)

                # find Node objects that we are targeting with trigger action
                targeted_nodes = self.collect_trigger_target_nodes(target_filter, nodes, policy_targets)

                # collect actions (interface operations) from targeted nodes
                collected_action = self.collect_trigger_action_from_interfaces(targeted_nodes, call_operation_name,
                                                                               action, inputs)
                if collected_action:
                    actions.append(collected_action)

        return actions

    # the next function is not part of the CollectorMixin because target_filter is policy only thing
    def resolve_event_filter(self, target_filter: Optional[Tuple[str, Any]],
                             nodes: Dict[str, Node]) -> Optional[Tuple[str, Any]]:
        """
        Resolve TOSCA policy trigger target filter (link trigger's target filter to targeted node object)
        :param target_filter: Target filter
        :param nodes: Node objects from TOSCA template
        :return: Resolved target filter
        """
        resolved_target_filter = None
        if target_filter:
            for node_name, node in nodes.items():
                if node_name == target_filter[0] or node.types[0] == target_filter[0]:
                    resolved_target_filter = node_name, node
                    break

        return resolved_target_filter

    # the next function is not part of the CollectorMixin because triggers are policy only thing
    def collect_triggers(self, service_ast: Dict[str, Any], policy_targets: Dict[str, Any],
                         nodes: Dict[str, Node]) -> Dict[str, Trigger]:
        """
        Collect TOSCA policy triggers
        :param service_ast: Abstract syntax tree dict
        :param policy_targets: TOSCA policy targets
        :param nodes: Node objects from TOSCA template
        :return: Triggers dict
        """
        # pylint: disable=too-many-locals
        typ = self.type.resolve_reference(service_ast)
        definitions = self.collect_trigger_definitions(typ, service_ast)
        assignments = self.get("triggers", {})

        duplicate_triggers = set(assignments.keys()).intersection(definitions.keys())
        if duplicate_triggers:
            for duplicate in duplicate_triggers:
                definitions.pop(duplicate)

        definitions.update(assignments)

        # TODO: optimize this code which is now nasty with a lot of parsing, looping and everything else.
        triggers = {}
        for name, definition in definitions.items():
            # collect and resolve target filter definition
            target_filter = None
            target_filter_definitions = definition.get("target_filter", None)
            if target_filter_definitions:
                target_node = target_filter_definitions.get("node", None)
                if target_node:
                    # resolve node reference and set target_filter
                    target_filter = (target_node.data, target_node.resolve_reference(service_ast))
                else:
                    self.abort("Cannot obtain node from target_filter.", self.loc)

            # check if target_filter also matches one node reference from policy's targets
            if target_filter and policy_targets and target_filter[0] not in list(policy_targets):
                self.abort(
                    f"The node reference: {target_filter[0]} from policy trigger's target_filter should be also "
                    f"present in policy's targets.", self.loc
                )

            # collect action definitions
            actions = self.collect_trigger_actions(definition, target_filter, nodes, policy_targets)

            trigger = Trigger(name=name,
                              event=definition.get("event", None),
                              target_filter=self.resolve_event_filter(target_filter, nodes),
                              condition=definition.get("condition", None),
                              action=actions)

            triggers[name] = trigger

        return triggers

    def concat(self, params):
        return "".join([str(Value(None, True, param).eval(self, '')) for param in params])

    def get_property(self, params):
        host, prop, *rest = params

        if host != 'SELF':
            raise RuntimeError(f'unknown host: {host}')

        if prop in self.collected_properties:
            return self.collected_properties[prop].eval(self, prop)
        else:
            raise RuntimeError(f'unknown property: {prop} ({list(self.collected_properties.keys())})')
