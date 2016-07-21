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

def runningvms()
    begin
        v = %x(vboxmanage list runningvms 2> .vagrant-error)
        running = v.lines()
        x = []
        running.each do |raw_line|
            # ll:
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
ALL_PROJECTS = YAML.load(IO.popen("/bin/bash -c \"source venv/bin/activate && ./.project.py --env=vagrant\"").read)

# essentially gives vagrant a project to use to prevent the prompt
if ['box'].include? VAGRANT_COMMAND
    prn "using default project 'basebox'"
    ENV['PROJECT'] = 'basebox--vagrant'
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
            
            INSTANCE_NAME = KEYED[opt] # ll: elife-lax--vagrant
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

PROJECT_NAME = SUPPORTED_PROJECTS[INSTANCE_NAME]  # ll: elife-lax
IS_MASTER = PROJECT_NAME == "master-server"

# necessary because we allow passing a project's name in via an ENV var
if not SUPPORTED_PROJECTS.has_key? INSTANCE_NAME
    prn "unknown project '#{INSTANCE_NAME}'"
    prn "known projects: " + SUPPORTED_PROJECTS.keys.join(', ')
    abort 
end

cmd = "/bin/bash -c \"source venv/bin/activate && ./.project.py #{PROJECT_NAME}\""
PRJ = YAML.load(IO.popen(cmd).read)

#PP.pp PRJ
#abort

# every project needs to tell us where to find it's formula for building it
if not PRJ.key?("formula-repo")
    prn "project data for '#{PROJECT_NAME}' has no key 'formula-repo'."
    prn "this value is used to clone the formula repository and build the project."
    prn
    prn "your `settings.yml` file contains project configuration locations"
    prn
    exit 1
end

def prj(key, default=nil)
    PRJ['vagrant'].fetch(key, default)
end

# if provisioning died before the custom ssh user (deploy user) can be created,
# set this to false and it will log-in as the default 'vagrant' user.
CUSTOM_SSH_USER = false
CUSTOM_SSH_USERNAME = "elife"
if ENV.fetch("CUSTOM_SSH_USER", nil)
    CUSTOM_SSH_USER = (true if ENV.fetch("CUSTOM_SSH_USER") =~ /^true$/i) || false
end

# finally! configure the beast
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
    # If true, then any SSH connections made will enable agent forwarding
    config.ssh.forward_agent = true # default: false
    config.ssh.insert_key = false

    if CUSTOM_SSH_USER and ["ssh", "ssh-config"].include? VAGRANT_COMMAND
        config.ssh.username = CUSTOM_SSH_USERNAME
        config.ssh.private_key_path = "payload/deploy-user.pem"
    end

    # setup any shared folders
    prj("shares", []).each {|d|
        if not File.directory?(d["host"])
            FileUtils.mkdir_p(d["host"])
        end
        config.vm.synced_folder(d["host"], d["guest"], **d.fetch("opts", {}))
    }

    config.vm.define INSTANCE_NAME do |project|
        project.vm.box = prj("box")
        project.vm.box_url = prj("box-url")
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

        formula = PRJ.fetch("formula-repo", nil)
        using_formula = formula != nil and formula != ""

        if using_formula and not File.exists?("cloned-projects/#{PROJECT_NAME}")
            FileUtils.mkdir_p("cloned-projects/#{PROJECT_NAME}/")
        end

        if not using_formula
            # in some cases this is deliberate (master-server, ...?)
            prn
            prn "no 'formula-repo' value found for project '#{PROJECT_NAME}'"
            prn
        else
            # clone the formula repo if it doesn't exist. user is in charge of keeping this updated.
            if File.exists?("cloned-projects/#{PROJECT_NAME}/.git")
                prn runcmd("cd cloned-projects/#{PROJECT_NAME}/ && git pull")
            else
                prn runcmd("git clone #{formula} cloned-projects/#{PROJECT_NAME}/")
            end
            # mount salt directories
            project.vm.synced_folder "cloned-projects/#{PROJECT_NAME}/", "/project"
        end

        # bootstrap Saltstack
        project.vm.provision("shell", path: "scripts/bootstrap.sh", keep_color: true, privileged: false, \
            args: [PRJ["salt"], INSTANCE_NAME, String(IS_MASTER), "noipfromhere"])
        
        if not IS_MASTER
            # configure Salt, call highstate
            project.vm.provision("shell", path: "scripts/init-vagrant-minion.sh", keep_color: true, privileged: false)
        else
            # configure the instance as if it were a master server. 
            # script assumes root access
            pillar_repo = "https://github.com/elifesciences/builder-private-example"
            project.vm.provision("shell", path: "scripts/init-master.sh", keep_color: true, privileged: true, \
                args: [INSTANCE_NAME, pillar_repo])
            project.vm.provision("shell", path: "scripts/update-master.sh", keep_color: true, privileged: true)
        end

        # tell the machine to update itself
        project.vm.provision("shell", path: "scripts/highstate.sh", keep_color: true, privileged: true)

        if File.exist? "scripts/customize.sh"
            project.vm.provision "shell", path: "scripts/customize.sh", keep_color: true, privileged: true
        end

    end # ends project configure

end # ends vagrant configure
