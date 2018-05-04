elifePipeline {

    def commit
    stage 'Checkout', {
        checkout scm
        commit = elifeGitRevision()
        // temporary
        elifeNotifyAtomist 'STARTED', 'STARTED'
    }

    stage 'Update', {
        sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent'
        sh 'rm -rf .tox'
    }

    stage 'Scrub', {
        withCommitStatus({
            sh './.ci-scrub.sh'
        }, 'scrub', commit)
    }

    stage 'Static checking', {
        elifeLocalTests()
    }

    lock('builder') {
        def pythons = ['py27', 'py35']
        def actions = [:]
        for (int i = 0; i < pythons.size(); i++) {
            def python = pythons.get(i)
            actions["Test ${python}"] = {
                withCommitStatus({
                    try {
                        sh "tox -e ${python}"
                    } finally {
                        step([$class: "JUnitResultArchiver", testResults: "build/pytest-${python}.xml"])
                    }
                }, python, commit)
            }
        }
        // currently unstable due to CloudFormation rate limiting
        //parallel actions
        stage "Test py27", {
            actions["Test py27"]() 
        }
        stage "Test py35", {
            actions["Test py35"]() 
        }
    }

    // temporary
    elifeNotifyAtomist 'SUCCESS'
}
