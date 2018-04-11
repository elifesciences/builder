elifePipeline {
    stage 'Checkout', {
        checkout scm
    }

    lock('builder') {
        stage 'Update', {
            sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent'
        }

        def pythons = ['py27', 'py35']
        def actions = [:]
        actions['Static checking'] = {
            sh './static_checking.sh'
        }
        for (int i = 0; i < pythons.size(); i++) {
            def python = pythons.get(i)
            actions["Python ${python}"] = {
                try {
                    sh "tox -e ${python}"
                } finally {
                    step([$class: "JUnitResultArchiver", testResults: "build/pytest-${python}.xml"])
                }
            }
        }
        parallel actions
    }
}
