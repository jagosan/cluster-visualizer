from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .models import ChaosScenario, FleetSpec
from .manager import TestbedManager, load_fleet_spec
from .chaos import ChaosInjector

logger = logging.getLogger(__name__)


def handle_up(args: argparse.Namespace) -> int:
    """Handle the 'up' command to bring up the testbed."""
    try:
        fleet_spec = load_fleet_spec(args.config)
        manager = TestbedManager(fleet_spec, mock_mode=args.mock)
        manager.up()
        
        if args.json:
            print(json.dumps({"status": "success", "action": "up"}, indent=2))
        else:
            print("Testbed is up and running.")
        return 0
    except Exception as e:
        logger.error(f"Failed to bring up testbed: {e}")
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_down(args: argparse.Namespace) -> int:
    """Handle the 'down' command to tear down the testbed."""
    try:
        fleet_spec = load_fleet_spec(args.config)
        manager = TestbedManager(fleet_spec, mock_mode=args.mock)
        manager.down()
        
        if args.json:
            print(json.dumps({"status": "success", "action": "down"}, indent=2))
        else:
            print("Testbed has been torn down.")
        return 0
    except Exception as e:
        logger.error(f"Failed to tear down testbed: {e}")
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_status(args: argparse.Namespace) -> int:
    """Handle the 'status' command to show testbed status."""
    try:
        fleet_spec = load_fleet_spec(args.config)
        manager = TestbedManager(fleet_spec, mock_mode=args.mock)
        report = manager.status()
        
        print(report.model_dump_json(indent=2))
        return 0
    except Exception as e:
        logger.error(f"Failed to get testbed status: {e}")
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_deploy_operator(args: argparse.Namespace) -> int:
    """Handle the 'deploy-operator' command to deploy an operator."""
    try:
        fleet_spec = load_fleet_spec(args.config)
        manager = TestbedManager(fleet_spec, mock_mode=args.mock)
        results = manager.deploy_operator(cluster_name=args.cluster)
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(json.dumps(results, indent=2))
        return 0
    except Exception as e:
        logger.error(f"Failed to deploy operator: {e}")
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_inject(args: argparse.Namespace) -> int:
    """Handle the 'inject' command to inject chaos."""
    try:
        scenario = ChaosScenario(
            scenario_type=args.scenario,
            cluster=args.cluster,
            target_resource=args.target,
            namespace=args.namespace
        )
        injector = ChaosInjector(mock_mode=args.mock)
        result = injector.inject(scenario)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        logger.error(f"Failed to inject chaos: {e}")
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def register_testbed_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register testbed subcommands with the given subparsers action."""
    testbed_parser = subparsers.add_parser(
        "testbed",
        help="Manage the testbed environment"
    )
    testbed_subparsers = testbed_parser.add_subparsers(
        dest="testbed_command",
        help="Testbed commands"
    )
    
    # Common arguments for all testbed subcommands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--config",
        type=str,
        default="testbeds/fleet-spec.yaml",
        help="Path to the fleet specification file"
    )
    common_parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode"
    )
    common_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )
    
    # up command
    up_parser = testbed_subparsers.add_parser(
        "up",
        parents=[common_parser],
        help="Bring up the testbed"
    )
    up_parser.set_defaults(func=handle_up)
    
    # down command
    down_parser = testbed_subparsers.add_parser(
        "down",
        parents=[common_parser],
        help="Tear down the testbed"
    )
    down_parser.set_defaults(func=handle_down)
    
    # status command
    status_parser = testbed_subparsers.add_parser(
        "status",
        parents=[common_parser],
        help="Show testbed status"
    )
    status_parser.set_defaults(func=handle_status)
    
    # deploy-operator command
    deploy_parser = testbed_subparsers.add_parser(
        "deploy-operator",
        parents=[common_parser],
        help="Deploy an operator to a cluster"
    )
    deploy_parser.add_argument(
        "--cluster",
        type=str,
        required=False,
        default=None,
        help="Name of the cluster to deploy the operator to (or omit for all)"
    )
    deploy_parser.add_argument(
        "--fleet",
        type=str,
        required=False,
        default=None,
        help="Name of the target fleet"
    )
    deploy_parser.set_defaults(func=handle_deploy_operator)
    
    # inject command
    inject_parser = testbed_subparsers.add_parser(
        "inject",
        parents=[common_parser],
        help="Inject chaos into the testbed"
    )
    inject_parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        help="Type of chaos scenario to inject"
    )
    inject_parser.add_argument(
        "--cluster",
        type=str,
        required=True,
        help="Name of the cluster to target"
    )
    inject_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target resource for chaos injection"
    )
    inject_parser.add_argument(
        "--namespace",
        type=str,
        required=False,
        default="default",
        help="Namespace for chaos injection (default: default)"
    )
    inject_parser.set_defaults(func=handle_inject)


def main(argv=None) -> int:
    """Main entry point for the testbed CLI."""
    parser = argparse.ArgumentParser(
        prog="cluster-vis testbed",
        description="Unified CLI for cluster-vis testbed commands"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Allow subcommands directly
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--config",
        type=str,
        default="testbeds/fleet-spec.yaml",
        help="Path to the fleet specification file"
    )
    common_parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode"
    )
    common_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    for p_name, p_func in [("up", handle_up), ("down", handle_down), ("status", handle_status)]:
        p = subparsers.add_parser(p_name, parents=[common_parser])
        p.set_defaults(func=p_func)

    p_dep = subparsers.add_parser("deploy-operator", parents=[common_parser])
    p_dep.add_argument("--cluster", type=str, default=None)
    p_dep.add_argument("--fleet", type=str, default=None)
    p_dep.set_defaults(func=handle_deploy_operator)

    p_inj = subparsers.add_parser("inject", parents=[common_parser])
    p_inj.add_argument("--scenario", type=str, required=True)
    p_inj.add_argument("--cluster", type=str, required=True)
    p_inj.add_argument("--target", type=str, required=True)
    p_inj.add_argument("--namespace", type=str, default="default")
    p_inj.set_defaults(func=handle_inject)

    # Also register testbed subcommands nested under 'testbed'
    register_testbed_subcommands(subparsers)
    
    args = parser.parse_args(argv)
    
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
