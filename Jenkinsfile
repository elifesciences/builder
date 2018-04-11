elifePipeline {
    stage 'Checkout', {
        checkout scm
    }

    lock('builder') {
        stage 'Update', {
            sh './update.sh --exclude virtualbox vagrant ssh-credentials ssh-agent'
        }

        stage 'Static checking', {
            sh './static_checking.sh'
        }

        def pythons = ['py27', 'py35']
        for (int i = 0; i < images.size(); i++) {
            def actions = [:]
            def python = pythons.get(i)
            actions["Python ${python}"] = {
                try {
                    sh "tox -e ${python}"
                } finally {
                    step([$class: "JUnitResultArchiver", testResults: "build/pytest-${python}.xml"])
                }
            }
            parallel actions
        }
    }
}
