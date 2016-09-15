elifePipeline {
    stage 'Checkout'
    checkout scm

    lock('builder') {
        stage 'Update'
        sh './update.sh --exclude virtualbox vagrant'

        stage 'Test'
        sh './project_tests.sh'
    }
}
