elifePipeline {
    stage 'Checkout', {
        checkout scm
    }

    lock('builder') {
        stage 'Update', {
            sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent'
        }

        stage 'Test', {
            try {
                    sh './project_tests.sh'
            } finally {
                step([$class: "JUnitResultArchiver", testResults: "build/junit-*.xml"])
            }
        }
    }
}
