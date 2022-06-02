# ==== Helper functions to be used across the cluster modules ====

# Returns the operating system name (e.g. Suse, RedHat)
def get_os_name(module, result):
    cmd = "egrep '^NAME=' /etc/os-release | awk -F'[=]' '{print $2}' | tr -d '\"[:space:]'"
    rc, out, err = module.run_command(cmd, use_unsafe_shell=True)
    if rc != 0:
        module.fail_json("Could not identify an OS distribution", **result)
    else:
        if "SLES" in out:
            return "Suse"
        elif "RedHat" in out:
            return "RedHat"
        else:
            module.fail_json("Unrecognized linux distribution", **result)

# Returns the operating system major version (e.g. 8)
def get_os_version(module, result):
    cmd = "egrep '^VERSION_ID=' /etc/os-release | awk -F'[=]' '{print $2}' | tr -d '\"[:space:]'"
    rc, out, err = module.run_command(cmd, use_unsafe_shell=True)
    if rc != 0:
        module.fail_json("Could not identify OS version", **result)
    else:
        return out.split('.')[0]

# Executes a command and handles the success or failure
def execute_command(module, result, cmd, success, failure, unsafe=False):
    rc, out, err = module.run_command(cmd, use_unsafe_shell=unsafe)
    if rc == 0:
        result["message"] += success
        return out
    else:
        result["changed"] = False
        result["stdout"] = out
        result["error_message"] = err
        result["command_used"] = cmd
        module.fail_json(msg=failure, **result)