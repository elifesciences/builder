elifePipeline {
    stage 'Checkout'
    checkout scm

    stage 'Update'
    sh './update.sh --exclude virtualbox vagrant'

    stage 'Test'
    sh './test.sh'
}
