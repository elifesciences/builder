elifePipeline {
    def pythonVersions = ['3.8', '3.9', '3.10']
    def commit
    stage 'Checkout', {
        checkout scm
        commit = elifeGitRevision()
    }

    def versionActions = [:]
    pythonVersions.each { pythonVersion ->
        versionActions['Python ' + pythonVersion] = {
            lock('builder') {
                stage 'Python ' + pythonVersion + ': Update', {
                    sh 'mise exec python@${pythonVersion} -- ./update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent vault'
                }

                stage 'Python ' + pythonVersion + ': .ci/ checks', {
                    def checkActions = [:]
                    checkActions['lint'] = elifeLocalTests('mise exec python@${pythonVersion} -- ./.ci/lint')
                    checkActions['projects-smoke'] = elifeLocalTests('mise exec python@${pythonVersion} -- ./.ci/projects-smoke')
                    checkActions['scrub'] = elifeLocalTests('mise exec python@${pythonVersion} -- ./.ci/scrub')
                    checkActions['shell-checking'] = elifeLocalTests('mise exec python@${pythonVersion} -- ./.ci/shell-checking')
                    parallel checkActions
                }

                stage 'Python ' + pythonVersion + ': Project tests', {
                    withCommitStatus({
                        try {
                            sh "BUILDER_INTEGRATION_TESTS=1 JUNIT_OUTPUT_ID=py${pythonVersion} mise exec python@${pythonVersion} -- ./test.sh"
                        } finally {
                            // https://issues.jenkins-ci.org/browse/JENKINS-27395?focusedCommentId=345589&page=com.atlassian.jira.plugin.system.issuetabpanels%3Acomment-tabpanel#comment-345589
                            junit testResults: "build/pytest-py${pythonVersion}.xml"
                        }
                    }, "py" + pythonVersion, commit)
                }
            }
        }
    }

    parallel versionActions

    stage 'Downstream', {
        elifeMainlineOnly {
            build job: '/release/release-builder-jenkins', wait: false
        }
    }
}
