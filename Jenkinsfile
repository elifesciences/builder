elifePipeline {

    def commit
    stage 'Checkout', {
        checkout scm
        commit = elifeGitRevision()
    }

    stage 'Update', {
        sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent vault'
        sh 'rm -rf .tox'
    }

    stage 'Scrub', {
        withCommitStatus({
            sh './.ci-scrub.sh'
        }, 'scrub', commit)
    }

    stage '.ci/ checks', {
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
            def py2Actions = [
                'host': { actions["Test py27"]() },
                'docker': {
                    withCommitStatus({
                        elifeOnNode({
                            checkout scm
                            sh './docker-smoke.sh 2'
                        }, 'containers--medium')
                    }, 'docker-py27', commit)
                }
            ]
            parallel py2Actions
        }
        stage "Test py35", {
            def py3Actions = [
                'host': { actions["Test py35"]() },
                'docker': {
                    withCommitStatus({
                        elifeOnNode({
                            checkout scm
                            sh './docker-smoke.sh 3'
                        }, 'containers--medium')
                    }, 'docker-py27', commit)
                }
            ]
            parallel py3Actions
        }
    }

    elifeMainlineOnly {
        stage 'Deploy to Alfred', {
            sh 'cd /srv/builder && git pull && . && ./update.sh --exclude virtualbox vagrant vault ssh-agent ssh-credentials'
        }
    }
}
