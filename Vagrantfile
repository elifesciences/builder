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

def runningvms()
    begin
        v = %x(vboxmanage list runningvms 2> .vagrant-error)
        running = v.lines()
        x = []
        running.each do |raw_line|
            # ll:
            # "builder_elife-lax-dev_1436877493449_44526" {4fdd43b7-5732-4d14-8f0d-cef087a5e650}
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
    ENV['PROJECT'] = 'basebox-dev'
end

# create a dev instance of all available projects
SUPPORTED_PROJECTS = {}
ALL_PROJECTS.each do |key, data|
    SUPPORTED_PROJECTS[key + "-dev"] = key
end

if not ENV['PROJECT']
    prn "You must select a project:"
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
            
            if default_project
                prn "> (" + default_project + ")"
            else
                prn "> ", false
            end
            opt = STDIN.gets.chomp.strip.downcase
            opt = Integer(opt) rescue false
            prn
            if not opt
                if default_project
                    PROJECT_NAME = default_project
                    break
                end
                prn "a number is required"
                next
            elsif opt > SUPPORTED_PROJECTS.length or opt < 1
                prn "a number in the range 1 to #{SUPPORTED_PROJECTS.length} is required"
                next
            end
            
            PROJECT_NAME = KEYED[opt]
            break
        end
        
        # remember the selected project
        FileUtils.mkdir_p('projects/elife/')
        fh = File.open('projects/elife/.vproject', 'w')
        fh.write(PROJECT_NAME)
        fh.close()
        
    rescue Interrupt
        abort ".. interrupt caught, aborting"
    end

elsif
    PROJECT_NAME = ENV['PROJECT']
end

# necessary because we allow passing a project's name in via an ENV var
if not SUPPORTED_PROJECTS.has_key? PROJECT_NAME
    prn "unknown project '#{PROJECT_NAME}'"
    prn "known projects: " + SUPPORTED_PROJECTS.keys.join(', ')
    abort 
end

cmd = "/bin/bash -c \"source venv/bin/activate && ./.project.py #{PROJECT_NAME.chomp('-dev')}\""
PRJ = YAML.load(IO.popen(cmd).read)

#PP.pp PRJ
#abort

def prj(key, default=nil)
    PRJ['vagrant'].fetch(key, default)
end

# if provisioning died before the custom ssh user (deploy user) can be created,
# set this to false and it will log-in as the default 'vagrant' user.
CUSTOM_SSH_USER = true
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

    config.vm.define PROJECT_NAME do |project|
        project.vm.box = prj("box")
        project.vm.box_url = prj("box-url")
        project.vm.host_name = PROJECT_NAME
        prn " [info] hostname is #{PROJECT_NAME} (this affects Salt configuration)"
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

        # mount salt directories
        project.vm.synced_folder "salt/salt/", "/srv/salt/"
        project.vm.synced_folder "salt/dev-pillar/", "/srv/dev-pillar/"
        project.vm.synced_folder "salt/pillar/", "/srv/pillar/"

        # global shared folder
        project.vm.synced_folder "public/", "/srv/public/", :mount_options => [ "dmode=777", "fmode=777" ]

        # bootstrap
        project.vm.provision "shell", path: "scripts/bootstrap.sh", args: [PRJ["salt"]], privileged: false
        project.vm.provision "shell", path: "scripts/init-minion.sh", privileged: false

    end # ends project configure

end # ends vagrant configure
