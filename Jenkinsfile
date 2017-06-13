elifePipeline {
    stage 'Checkout', {
        checkout scm
    }

    lock('builder') {
        stage 'Update', {
            sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent'
        }

        stage 'Test', {
            sh './project_tests.sh'
        }
    }
}
