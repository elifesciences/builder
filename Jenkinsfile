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
        def actions = [:]
        def python = 'py3'
        
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
                    sh "./docker-smoke.sh"
                }
            }, "docker-${python}", commit)
        }

        stage 'Project tests', {
            parallel actions
        }
    }

    stage 'Downstream', {
        elifeMainlineOnly {
            build job: '/release/release-builder-jenkins', wait: false
        }
    }
}
