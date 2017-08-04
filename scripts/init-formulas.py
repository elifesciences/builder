#!/usr/bin/python
# AWS MASTERLESS ONLY
# downloads and configures formulas using /etc/build-vars.json.b64
# Vagrant initialises the formulas in the Vagrantfile

# init formulas


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
                prn runcmd("cd #{formula_path}/ && git pull")
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
        # /srv/custom/salt/
        # /cloned-projects/builder-base-formula/salt/
        # /srv/salt/
        # [/cloned-projects/any-other-dependent-formulas/]

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


if [ ! -d /vagrant ]; then
    # no Vagrant around with shared directories of things
    # we need to make sure they're available for the rest of the script

    mkdir /fake-vagrant
    ln -sfT /fake-vagrant /vagrant # good enough for now :(
    
    mkdir -p /project/salt/pillar

    # TODO: clone project formula
    # TODO: upload custom minion file

fi

