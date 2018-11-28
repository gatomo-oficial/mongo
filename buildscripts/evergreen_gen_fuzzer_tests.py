#!/usr/bin/env python
"""Generate fuzzer tests to run in evergreen in parallel."""

from __future__ import absolute_import

import argparse
import math
import os

from collections import namedtuple

import yaml

from shrub.config import Configuration
from shrub.command import CommandDefinition
from shrub.task import TaskDependency
from shrub.variant import DisplayTaskDefinition
from shrub.variant import TaskSpec

CONFIG_DIRECTORY = "generated_resmoke_config"

ConfigOptions = namedtuple("ConfigOptions", [
    "num_files",
    "num_tasks",
    "resmoke_args",
    "npm_command",
    "jstestfuzz_vars",
    "name",
    "variant",
    "continue_on_failure",
    "should_shuffle",
    "timeout_secs",
    "use_multipath",
])


def _get_config_value(attrib, cmd_line_options, config_file_data, required=False, default=None):
    """
    Get the configuration value to use.

    First use command line options, then config file option, then the default. If required is
    true, throw an exception if the value is not found.

    :param attrib: Attribute to search for.
    :param cmd_line_options: Command line options.
    :param config_file_data: Config file data.
    :param required: Is this option required.
    :param default: Default value if option is not found.
    :return: value to use for this option.
    """
    value = getattr(cmd_line_options, attrib, None)
    if value:
        return value

    value = config_file_data.get(attrib)
    if value:
        return value

    if required:
        raise ValueError("{0} must be specified".format(attrib))

    return default


def _get_config_options(cmd_line_options, config_file):
    """
    Get the configuration to use.

    Command line options override config files options.

    :param cmd_line_options: Command line options specified.
    :param config_file: config file to use.
    :return: ConfigOptions to use.
    """
    config_file_data = {}
    if config_file:
        with open(config_file) as file_handle:
            config_file_data = yaml.load(file_handle)

    num_files = int(
        _get_config_value("num_files", cmd_line_options, config_file_data, required=True))
    num_tasks = int(
        _get_config_value("num_tasks", cmd_line_options, config_file_data, required=True))
    resmoke_args = _get_config_value("resmoke_args", cmd_line_options, config_file_data, default="")
    npm_command = _get_config_value("npm_command", cmd_line_options, config_file_data,
                                    default="jstestfuzz")
    jstestfuzz_vars = _get_config_value("jstestfuzz_vars", cmd_line_options, config_file_data,
                                        default="")
    name = _get_config_value("name", cmd_line_options, config_file_data, required=True)
    variant = _get_config_value("build_variant", cmd_line_options, config_file_data, required=True)
    continue_on_failure = _get_config_value("continue_on_failure", cmd_line_options,
                                            config_file_data, default="false")
    should_shuffle = _get_config_value("should_shuffle", cmd_line_options, config_file_data,
                                       default="false")
    timeout_secs = _get_config_value("timeout_secs", cmd_line_options, config_file_data,
                                     default="1800")
    use_multipath = _get_config_value("task_path_suffix", cmd_line_options, config_file_data,
                                      default=False)

    return ConfigOptions(num_files, num_tasks, resmoke_args, npm_command, jstestfuzz_vars, name,
                         variant, continue_on_failure, should_shuffle, timeout_secs, use_multipath)


def _name_task(parent_name, task_index, total_tasks):
    """
    Create a zero-padded sub-task name.

    :param parent_name: Name of the parent task.
    :param task_index: Index of this sub-task.
    :param total_tasks: Total number of sub-tasks being generated.
    :return: Zero-padded name of sub-task.
    """
    index_width = int(math.ceil(math.log10(total_tasks)))
    return "{0}_{1}".format(parent_name, str(task_index).zfill(index_width))


def _generate_evg_tasks(options):
    """
    Generate an evergreen configuration for fuzzers based on the options given.

    :param options: task options.
    :return: An evergreen configuration.
    """
    evg_config = Configuration()

    task_names = []
    task_specs = []

    for task_index in range(options.num_tasks):
        name = _name_task(options.name, task_index, options.num_tasks) + "_" + options.variant
        task_names.append(name)
        task_specs.append(TaskSpec(name))
        task = evg_config.task(name)

        commands = [CommandDefinition().function("do setup")]
        if options.use_multipath:
            commands.append(CommandDefinition().function("do multiversion setup"))

        commands.append(CommandDefinition().function("run jstestfuzz").vars({
            "jstestfuzz_vars":
                "--numGeneratedFiles {0} {1}".format(options.num_files, options.jstestfuzz_vars),
            "npm_command":
                options.npm_command
        }))
        run_tests_vars = {
            "continue_on_failure": options.continue_on_failure,
            "resmoke_args": options.resmoke_args,
            "should_shuffle": options.should_shuffle,
            "task_path_suffix": options.use_multipath,
            "timeout_secs": options.timeout_secs,
        }

        commands.append(CommandDefinition().function("run tests").vars(run_tests_vars))
        task.dependency(TaskDependency("compile")).commands(commands)

    dt = DisplayTaskDefinition(options.name).execution_tasks(task_names)\
        .execution_task("{0}_gen".format(options.name))
    evg_config.variant(options.variant).tasks(task_specs).display_task(dt)

    return evg_config


def main():
    """Generate fuzzer tests to run in evergreen."""
    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument("--expansion-file", dest="expansion_file", type=str,
                        help="Location of expansions file generated by evergreen.")
    parser.add_argument("--num-files", dest="num_files", type=int,
                        help="Number of files to generate per task.")
    parser.add_argument("--num-tasks", dest="num_tasks", type=int,
                        help="Number of tasks to generate.")
    parser.add_argument("--resmoke-args", dest="resmoke_args", help="Arguments to pass to resmoke.")
    parser.add_argument("--npm-command", dest="npm_command", help="npm command to run for fuzzer.")
    parser.add_argument("--jstestfuzz-vars", dest="jstestfuzz_vars",
                        help="options to pass to jstestfuzz.")
    parser.add_argument("--name", dest="name", help="name of task to generate.")
    parser.add_argument("--variant", dest="build_variant", help="build variant to generate.")
    parser.add_argument("--use-multipath", dest="task_path_suffix",
                        help="Task path suffix for multipath generated tasks.")
    parser.add_argument("--continue-on-failure", dest="continue_on_failure",
                        help="continue_on_failure value for generated tasks.")
    parser.add_argument("--should-shuffle", dest="should_shuffle",
                        help="should_shuffle value for generated tasks.")
    parser.add_argument("--timeout-secs", dest="timeout_secs",
                        help="timeout_secs value for generated tasks.")

    options = parser.parse_args()

    config_options = _get_config_options(options, options.expansion_file)

    evg_config = _generate_evg_tasks(config_options)

    if not os.path.exists(CONFIG_DIRECTORY):
        os.makedirs(CONFIG_DIRECTORY)

    with open(os.path.join(CONFIG_DIRECTORY, config_options.name + ".json"), "w") as file_handle:
        file_handle.write(evg_config.to_json())


if __name__ == '__main__':
    main()
