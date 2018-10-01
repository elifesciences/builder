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
        def majorVersions = [2, 3]
        def actions = [:]
        for (int i = 0; i < pythons.size(); i++) {
            def python = pythons.get(i)
            def majorVersion = majorVersions.get(i)
            actions["Test ${python}"] = {
                withCommitStatus({
                    try {
                        sh "tox -e ${python}"
                    } finally {
                        // https://issues.jenkins-ci.org/browse/JENKINS-27395?focusedCommentId=345589&page=com.atlassian.jira.plugin.system.issuetabpanels%3Acomment-tabpanel#comment-345589
                        junit testResults: "build/pytest-${python}.xml"
                    }
                }, python, commit)
            }

            actions["Docker ${python}"] = {
                withCommitStatus({
                    node('containers-jenkins-plugin') {
                        checkout scm
                        sh "./docker-smoke.sh ${majorVersion}"
                    }
                }, "docker-${python}", commit)
            }
        }

        parallel actions
    }

    elifeMainlineOnly {
        stage 'Deploy to Alfred', {
            sh 'cd /srv/builder && git pull && . && ./update.sh --exclude virtualbox vagrant vault ssh-agent ssh-credentials'
        }
    }
}
