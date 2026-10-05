import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root
    property var settings: ({})
    property bool stopping: false
    readonly property string helperPath: Qt.resolvedUrl("bin/omacorsair.py").toString().replace(/^file:\/\//, "")

    Process {
        id: worker
        command: ["/usr/bin/python3", "-I", root.helperPath, "daemon"].concat(root.settings.rawColor === true ? ["--raw"] : [])
        running: true
        stderr: SplitParser {
            onRead: data => console.log(String(data).slice(0, 1024))
        }
        onExited: (code, status) => {
            if (!root.stopping) {
                console.log("[omacorsair] helper exited (" + code + "), retrying in 5 seconds")
                retry.start()
            }
        }
    }

    Timer {
        id: retry
        interval: 5000
        onTriggered: worker.running = true
    }

    Component.onDestruction: {
        root.stopping = true
        retry.stop()
        if (worker.running) worker.signal(15)
    }
}
