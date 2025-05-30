# -*- coding: utf-8 -*-
# -*- mode: ruby -*-
# vi: set ft=ruby :

['yaml', 'fileutils', 'pp'].each{| mod | require mod }

def prn(out="", nl=true)
    STDERR.print out
    STDERR.print "\n" if nl
    STDERR.flush
    nil
end

def runcmd(cmd)
    #prn "running command: " + cmd
    output = nil
    IO.popen(cmd) do |io|
        output = io.read
    end
    exit_status = $?.exitstatus
    if exit_status != 0
      throw "Command '#{cmd}' exited with #{exit_status}"
    end
    return output
end

def project_cmd(argstr)
    executable = "venv/bin/python"
    end
    cmd = "/bin/bash -c \"./#{executable} .project.py #{argstr}\""
    prn(cmd)
    return YAML.load(IO.popen(cmd).read)
end

def runningvms()
    begin
        v = %x(vboxmanage list runningvms 2> .vagrant-error)
        running = v.lines()
        x = []
        running.each do |raw_line|
            # "builder_elife-lax--vagrant_1436877493449_44526" {4fdd43b7-5732-4d14-8f0d-cef087a5e650}
            bits = raw_line.split("_")
            x.push(bits[1])
        end
        x
    rescue
        prn "* error finding running vms"
        throw
    end
end

VAGRANTFILE_API_VERSION = "2"
VAGRANT_COMMAND = ARGV[0]
VAGRANT_VERSION = %x(vagrant --version).gsub(/[^\d\.]/, "") # looks like: 1.7.4
# all *VAGRANT* projects
ALL_PROJECTS = project_cmd("--env=vagrant")

# essentially gives vagrant a project to use to prevent the prompt
if ['box'].include? VAGRANT_COMMAND
    prn "using default project 'basebox'"
    ENV['PROJECT'] = 'basebox'
end

# create a dev instance of all available projects
SUPPORTED_PROJECTS = {}
ALL_PROJECTS.each do |key, data|
    SUPPORTED_PROJECTS[key + "--vagrant"] = key
end

if ENV['PROJECT']
    INSTANCE_NAME = ENV['PROJECT'] + "--vagrant"
else
    prn "Select a project:"
    KEYED = {}
    SUPPORTED_PROJECTS.each_with_index do |k,i|
        KEYED[i+1] = k[0]
    end

    default_project = nil
    if File.exists?('projects/elife/.vproject')
        fh = File.open('projects/elife/.vproject', 'r')
        default_project = fh.read()
        fh.close()
    end
    DEFAULT_AVAILABLE = SUPPORTED_PROJECTS.include?(default_project)

    vmlist = runningvms()

    begin
        while true
            prn
            KEYED.each do |k,i|
                if vmlist.include?(i)
                    prn "#{k} - #{i}  [running]"
                else
                    prn "#{k} - #{i}"
                end
            end

            if DEFAULT_AVAILABLE
                prn "> (" + default_project + ")"
            else
                prn "> ", false
            end
            opt = STDIN.gets.chomp.strip.downcase
            opt = Integer(opt) rescue false
            prn
            if not opt
                if DEFAULT_AVAILABLE
                    INSTANCE_NAME = default_project
                    break
                end
                prn "a number is required"
                next
            elsif opt > SUPPORTED_PROJECTS.length or opt < 1
                prn "a number in the range 1 to #{SUPPORTED_PROJECTS.length} is required"
                next
            end

            INSTANCE_NAME = KEYED[opt] # "elife-lax--vagrant"
            break
        end

        # remember the selected project
        FileUtils.mkdir_p('projects/elife/')
        fh = File.open('projects/elife/.vproject', 'w')
        fh.write(INSTANCE_NAME)
        fh.close()

    rescue Interrupt
        abort ".. interrupt caught, aborting"
    end

end

PROJECT_NAME = SUPPORTED_PROJECTS[INSTANCE_NAME]  # "elife-lax"
IS_MASTER = PROJECT_NAME == "master-server"

# necessary because we allow passing a project's name in via an ENV var
if not SUPPORTED_PROJECTS.has_key? INSTANCE_NAME
    prn "unknown project '#{INSTANCE_NAME}'"
    prn "known projects: " + SUPPORTED_PROJECTS.keys.join(', ')
    abort
end

PRJ = project_cmd(PROJECT_NAME)

#PP.pp PRJ
#abort

# every project needs to tell us where to find it's formula for building it
if not PRJ.key?("formula-repo")
    prn "project data (projects/elife.yaml) for '#{PROJECT_NAME}' has no key 'formula-repo'."
    prn "this value is used to clone the formula repository and build the project."
    prn
    exit 1
end

def prj(key, default=nil)
    PRJ['vagrant'].fetch(key, default)
end

# ask user if they want to use the large amount of RAM requested
RAM_CHECK_THRESHOLD = 4096
if (prj('ram').to_i > RAM_CHECK_THRESHOLD) and ['up', 'reload'].include? VAGRANT_COMMAND
    requested = prj('ram')

    flag = ".#{PROJECT_NAME}-#{requested}.flag"

    if File.exists?(flag)
        prn "found #{flag}, skipping excessive ram check"
    else
        prn "project is requesting a large amount of RAM (#{requested}MB)"

        prn "1 - #{RAM_CHECK_THRESHOLD}MB"
        prn "2 - #{requested}MB"
        prn "> (#{RAM_CHECK_THRESHOLD}MB)"
        begin
            opt = STDIN.gets.chomp.strip.downcase
            opt = Integer(opt) rescue false
        rescue Interrupt
            abort
        end

        options = {1 => RAM_CHECK_THRESHOLD, 2 => prj('ram')}

        if not opt
            PRJ['vagrant']['ram'] = RAM_CHECK_THRESHOLD
        elsif options.keys.include? opt
            PRJ['vagrant']['ram'] = options[opt.to_i]
            FileUtils.touch(flag)
        else
            prn "unrecognized input, quitting"
            exit()
        end
    end
end

# if provisioning died before the custom ssh user (deploy user) can be created,
# set this to false and it will log-in as the default 'vagrant' user.
CUSTOM_SSH_KEY = File.expand_path(ENV.fetch("CUSTOM_SSH_KEY", "~/.ssh/id_rsa"))
CUSTOM_SSH_USER = File.exists?(CUSTOM_SSH_KEY)
CUSTOM_SSH_USERNAME = "elife"
if ENV.fetch("CUSTOM_SSH_USER", nil)
    CUSTOM_SSH_USER = (true if ENV.fetch("CUSTOM_SSH_USER") =~ /^true$/i) || false
end

# finally! configure the beast
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
    # if true, then any SSH connections made will enable agent forwarding
    config.ssh.forward_agent = true # default: false
    config.ssh.insert_key = false

    if CUSTOM_SSH_USER and ["ssh", "ssh-config"].include? VAGRANT_COMMAND
        prn "Using ssh key #{CUSTOM_SSH_KEY}"
        config.ssh.username = CUSTOM_SSH_USERNAME
        config.ssh.private_key_path = File.expand_path(CUSTOM_SSH_KEY)
    end

    # setup any shared folders
    prj("shares", []).each {|d|
        if not File.directory?(d["host"])
            FileUtils.mkdir_p(d["host"])
        end
        config.vm.synced_folder(d["host"], d["guest"], **d.fetch("opts", {}))
    }

    config.vm.define INSTANCE_NAME do |project|
        project.vm.box_check_update = false # don't gab to the internet, please :(
        project.vm.box = prj("box")
        project.vm.host_name = INSTANCE_NAME
        prn " [info] hostname is #{INSTANCE_NAME} (this affects Salt configuration)"
        project.vm.network :private_network, ip: prj("ip")

        # setup any port forwarding
        prj("ports", {}).each{|host_port, guest_port|
            #prn("host #{host_port} guest #{guest_port}")
            if guest_port.kind_of?(Hash)
                # we have more complex mapping requirements than hostport:guestport
                guest_opts = guest_port
                project.vm.network(:forwarded_port, host: host_port, **guest_opts)
            else
                project.vm.network(:forwarded_port, host: host_port, guest: guest_port)
            end
        }

        project.vm.provider :virtualbox do |vb|
            vb.customize ["modifyvm", :id, "--cpus", prj("cpus")]
            vb.customize ["modifyvm", :id, "--memory", prj("ram")]
            # allows symlinks to be created
            # bug in virtualbox 5.0.4 causing symlinks with '..' in them to fail with protocol error
            vb.customize ["setextradata", :id, "VBoxInternal2/SharedFoldersEnableSymlinksCreate/v-root", "1"]

            # speeds up downloads (supposedly):
            # https://github.com/mitchellh/vagrant/issues/1807#issuecomment-19132198
            vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
            vb.customize ["modifyvm", :id, "--natdnsproxy1", "on"]
            vb.customize ["modifyvm", :id, "--nictype1", "virtio"]
            # ensures vm doesn't guzzle cpu usage. default is 100%
            # Note: limiting the execution time of the virtual CPUs may induce guest timing problems.
            vb.customize ["modifyvm", :id, "--cpuexecutioncap", prj("cpucap")]
        end

        project.vm.provider :libvirt do |lv|
            lv.memory = prj("ram")
            lv.cpus = prj("cpus")
            lv.nic_model_type = "virtio"
            lv.volume_cache = "writeback"
        end

        formula = PRJ.fetch("formula-repo", nil)
        using_formula = formula != nil and formula != ""

        if using_formula
            # no need to attempt a clone/pull when ssh'ing or stopping a machine ...
            if ['up', 'provision', 'reload'].include? VAGRANT_COMMAND
                all_formulas = PRJ.fetch("formula-dependencies") + [formula]
                prn "formulas needed: #{all_formulas}"
                formula_paths = all_formulas.map {| formula |
                    # split the formula into two bits using '/', starting from the right
                    _, formula_name = formula.split(/\/([^\/]*)$/)
                    formula_path = "cloned-projects/#{formula_name}"
                    if not File.exists?(formula_path)
                        FileUtils.mkdir_p(formula_path)
                    end
                    # clone the formula repo if it doesn't exist, else update it
                    if File.exists?(formula_path + "/.git")
                        prn "Updating #{formula_path}..."
                        prn runcmd("cd #{formula_path}/ && git pull || echo trouble pulling")
                    else
                        prn "Cloning #{formula_path}..."
                        prn runcmd("git clone #{formula} #{formula_path}/")
                    end
                    formula_path
                }
                # write the minion file
                minion_cfg = YAML.load_file("scripts/salt/minion.template")

                project_formula = formula_paths.pop() # path to this project's formula
                more_base_paths = formula_paths.map{|p| "/vagrant/" + p + "/salt/"}

                # expected order:
                # /vagrant/custom-vagrant/salt/
                # /vagrant/cloned-projects/builder-base-formula/salt/
                # /project/salt/
                # [/vagrant/cloned-projects/any-other-dependent-formulas/]

                minion_cfg['file_roots']['base'].insert(1, more_base_paths[0]) # after /srv/custom/salt/
                rest_paths = more_base_paths[1..-1] # all paths except the first
                minion_cfg['file_roots']['base'].insert(3, *rest_paths)

                more_pillar_roots = more_base_paths.map{|p| p + "pillar/" }
                minion_cfg['pillar_roots']['base'].insert(2, *more_pillar_roots)

                # write minion file.
                # bootstrap script will find this file and use it
                File.open("scripts/salt/" + INSTANCE_NAME + ".minion", "w") {|f| f.write minion_cfg.to_yaml }

                # mount formula as salt directory
                project.vm.synced_folder project_formula, "/project"
            end
        else
            prn "no 'formula-repo' value found for project '#{PROJECT_NAME}'"
        end

        # makes the current user's pub key available within the guest.
        # Salt will pick up on it's existence and add it to the deploy user's
        # `./ssh/authorised_keys` file allowing login.
        # ssh-agent provides communication with Github
        if File.exists?(CUSTOM_SSH_KEY + ".pub")
          runcmd("cp #{CUSTOM_SSH_KEY}.pub custom-vagrant/id_rsa.pub")
        end

        # bootstrap Saltstack
        project.vm.provision("shell",
            path: "scripts/bootstrap.sh", \
            keep_color: true, \
            privileged: true, \
            env: {'grain_project': PROJECT_NAME},
            args: [PRJ["salt"], INSTANCE_NAME, String(IS_MASTER)])

        # link up formulas
        project.vm.provision("shell", \
            path: "scripts/init-vagrant-formulas.sh", \
            keep_color: true, \
            privileged: true, \
            env: { 'BUILDER_TOPFILE': ENV['BUILDER_TOPFILE'] }, \
            args: [INSTANCE_NAME])

        # configure the instance as if it were a master server
        if IS_MASTER
            pillar_repo = "https://github.com/elifesciences/builder-private-example"
            configuration_repo = "https://github.com/elifesciences/builder-configuration"
            all_formulas = project_cmd("--formula")
            project.vm.provision("shell", path: "scripts/init-master.sh", \
                keep_color: true, privileged: true, args: [INSTANCE_NAME, pillar_repo, configuration_repo, all_formulas.join(' ')])
            master_configuration = project_cmd("master-server --task salt-master-config | tee etc-salt-master")
            project.vm.provision("file", source: "./etc-salt-master", destination: "/tmp/etc-salt-master")
            project.vm.provision("shell", inline: "sudo mv /tmp/etc-salt-master /etc/salt/master")

            # this script is called regularly on master server to sync project formulas
            project.vm.provision("shell", path: "scripts/update-master.sh", \
                keep_color: true, privileged: true)
            project.vm.provision("shell", inline: "sudo cp /vagrant/scripts/update-master.sh /opt/update-master.sh && chmod +x /opt/update-master.sh")
        end

        # tell the machine to update itself
        project.vm.provision("shell", path: "scripts/highstate.sh", keep_color: true, privileged: true)

        if File.exist? "scripts/customize.sh"
            project.vm.provision "shell", path: "scripts/customize.sh", keep_color: true, privileged: true
        end

    end # ends project configure

end # ends vagrant configure
