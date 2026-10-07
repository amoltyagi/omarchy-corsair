import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
    id: root
    moduleName: "case.omacorsair"
    ipcTarget: "case.omacorsair"
    manageIpc: false
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    property var config: ({mode: "theme", color: "00aaff", accent: "ff4080", brightness: 100, vivid: true, speed: 50})
    property var device: ({connected: false, error: "Waiting for keyboard"})
    property string actionError: ""
    property var pendingUpdate: null
    property string requestedMode: ""
    property bool galleryExpanded: false
    property string category: "All"
    property var preview: []
    property var language: ({active: "us", label: "EN", name: "English (US)", available: [], layouts: []})
    readonly property var layoutChoices: language.layouts || []
    readonly property bool canSwitchLayout: layoutChoices.length > 1
    property string languageError: ""
    property bool languageRefreshQueued: false
    property bool baseColorDirty: false
    property bool accentColorDirty: false
    readonly property string helperPath: Qt.resolvedUrl("bin/omacorsair.py").toString().replace(/^file:\/\//, "")
    readonly property string layoutHelperPath: Qt.resolvedUrl("bin/layouts.py").toString().replace(/^file:\/\//, "")
    property var modes: [{id: "theme", name: "Theme sync", hint: "Follow your Omarchy theme", category: "Custom"}]
    readonly property string selectedMode: requestedMode || config.mode
    readonly property int modeIndex: Math.max(0, modes.findIndex(m => m.id === selectedMode))
    readonly property var currentLook: modes[modeIndex] || modes[0]
    readonly property var browseModes: modes.filter(m => category === "All" || m.category === category)
    readonly property var previewRows: preview.length ? preview : [14, 15, 15, 14, 13, 11].map(n => Array(n).fill("#222222"))
    readonly property var colors: [
        {name: "Red", hex: "ff2020"}, {name: "Orange", hex: "ff8000"},
        {name: "Gold", hex: "ffcc00"}, {name: "Green", hex: "20ff50"},
        {name: "Cyan", hex: "00ffee"}, {name: "Blue", hex: "0088ff"},
        {name: "Purple", hex: "8844ff"}, {name: "Pink", hex: "ff3090"},
        {name: "Ice", hex: "99ddff"}, {name: "White", hex: "ffffff"}
    ]

    function refresh() {
        if (!statusProc.running && !actionProc.running) statusProc.running = true
    }

    function refreshLanguage() {
        if (languageQuery.running) {
            languageRefreshQueued = true
            return
        }
        languageRefreshQueued = false
        languageQuery.running = true
    }

    function ingestLanguage(text) {
        try {
            language = JSON.parse(text)
            languageError = ""
        } catch (error) {
            languageError = "Couldn't read the current keyboard layout"
        }
    }

    function switchLanguage(code) {
        if (languageAction.running) return
        languageError = ""
        languageAction.command = ["/usr/bin/python3", "-I", layoutHelperPath].concat(code === "toggle" ? ["toggle"] : ["set", code])
        languageAction.running = true
    }

    function ingest(text) {
        try {
            var result = JSON.parse(text)
            if (result.config) {
                config = result.config
                if (!baseColorDirty && !baseField.activeFocus) baseField.text = "#" + config.color
                if (!accentColorDirty && !accentField.activeFocus) accentField.text = "#" + config.accent
            }
            if (result.device) device = result.device
            if (result.catalog) modes = result.catalog
            if (result.preview) preview = result.preview
            if (result.config && result.config.mode === requestedMode) requestedMode = ""
        } catch (error) {
            actionError = "Couldn't read keyboard status"
        }
    }

    function submit(update) {
        if (update.mode) requestedMode = update.mode
        if (actionProc.running) {
            pendingUpdate = Object.assign({}, pendingUpdate || {}, update)
            return
        }
        actionError = ""
        if (update.color) {
            baseColorDirty = false
            baseField.text = "#" + update.color.replace(/^#/, "")
        }
        if (update.accent) {
            accentColorDirty = false
            accentField.text = "#" + update.accent.replace(/^#/, "")
        }
        actionProc.command = ["/usr/bin/python3", "-I", helperPath, "set", JSON.stringify(update)]
        actionProc.running = true
    }

    function cycle(delta) {
        if (!modes.length) return
        var index = (modeIndex + delta + modes.length) % modes.length
        submit({mode: modes[index].id})
    }

    function surprise() {
        var choices = modes.filter(m => m.category !== "System" && m.id !== selectedMode && m.id !== "theme" && m.id !== "solid")
        if (choices.length) submit({mode: choices[Math.floor(Math.random() * choices.length)].id})
    }

    function applyCustom() {
        var base = baseField.text.trim()
        var accent = accentField.text.trim()
        if (!/^#?[0-9a-fA-F]{6}$/.test(base) || !/^#?[0-9a-fA-F]{6}$/.test(accent)) {
            actionError = "Enter six hex digits, for example #00AAFF"
            return
        }
        submit({mode: currentLook.custom ? currentLook.id : "solid", color: base, accent: accent})
    }

    // A bar surface exists per monitor, so this Panel is instantiated once per
    // screen, but an IPC target accepts only one handler. Only the instance on
    // the first screen registers; it then routes open/close/toggle to the
    // instance on the focused monitor (the same rule the shell uses for
    // `omarchy-shell shell toggle <id>`). If that screen goes away, the binding
    // re-evaluates and the instance on the new first screen takes over.
    readonly property string screenName: QsWindow.window && QsWindow.window.screen ? String(QsWindow.window.screen.name || "") : ""
    readonly property bool ipcOwner: screenName !== "" && Quickshell.screens.length > 0 && String(Quickshell.screens[0].name || "") === screenName

    function livePanels() {
        var items = root.bar && typeof root.bar.moduleWidgets === "function" ? root.bar.moduleWidgets(root.moduleName) : []
        var panels = items.filter(item => item && typeof item.open === "function" && typeof item.close === "function")
        return panels.length ? panels : [root]
    }

    function focusedPanel(panels) {
        var monitor = Hyprland.focusedMonitor
        var name = monitor ? String(monitor.name || "") : ""
        if (name !== "") {
            for (var i = 0; i < panels.length; i++) {
                if (panels[i].screenName === name) return panels[i]
            }
        }
        return root
    }

    function openOnFocused() {
        var panels = livePanels()
        var target = focusedPanel(panels)
        panels.forEach(panel => { if (panel !== target && panel.opened) panel.close() })
        target.open()
    }

    function closeAll() {
        livePanels().forEach(panel => panel.close())
    }

    function toggleOnFocused() {
        var panels = livePanels()
        var openPanels = panels.filter(panel => panel.opened)
        if (openPanels.length) openPanels.forEach(panel => panel.close())
        else focusedPanel(panels).open()
    }

    // Other monitors' copies hold their own config/device snapshot; refresh
    // them after a change so IPC next/previous (served by one copy) never
    // starts from a stale look.
    function refreshPeers() {
        livePanels().forEach(panel => { if (panel !== root) panel.refresh() })
    }

    IpcHandler {
        enabled: root.ipcOwner
        target: root.ipcTarget
        function open(): void { root.openOnFocused() }
        function close(): void { root.closeAll() }
        function toggle(): void { root.toggleOnFocused() }
        function setColor(color: string): void { root.submit({mode: "solid", color: color}) }
        function setMode(mode: string): void { root.submit({mode: mode}) }
        function next(): void { root.cycle(1) }
        function previous(): void { root.cycle(-1) }
        function surprise(): void { root.surprise() }
        function toggleLanguage(): void { root.switchLanguage("toggle") }
        function setLanguage(language: string): void { root.switchLanguage(language) }
    }

    onOpenedChanged: {
        if (opened) {
            refresh()
            refreshLanguage()
            baseField.text = "#" + config.color
            accentField.text = "#" + config.accent
            baseColorDirty = false
            accentColorDirty = false
        }
    }

    Component.onCompleted: {
        refresh()
        refreshLanguage()
    }
    Timer { interval: root.currentLook.animated ? 700 : 1500; repeat: true; running: root.opened; onTriggered: root.refresh() }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event && (event.name === "activelayout" || event.name === "configreloaded")) languageDebounce.restart()
        }
    }
    Timer { id: languageDebounce; interval: 80; onTriggered: root.refreshLanguage() }
    Timer { interval: 10000; repeat: true; running: true; onTriggered: root.refreshLanguage() }
    Process {
        id: languageQuery
        command: ["/usr/bin/python3", "-I", root.layoutHelperPath, "status"]
        stdout: StdioCollector { onStreamFinished: if (text.trim()) root.ingestLanguage(text) }
        onExited: (code, status) => {
            if (code !== 0) root.languageError = "Couldn't query Hyprland keyboard layouts"
            if (root.languageRefreshQueued) Qt.callLater(root.refreshLanguage)
        }
    }
    Process {
        id: languageAction
        stdout: StdioCollector { onStreamFinished: if (text.trim()) root.ingestLanguage(text) }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) root.languageError = text.trim().slice(0, 300) }
        onExited: (code, status) => {
            if (code !== 0 && !root.languageError) root.languageError = "Couldn't change keyboard language"
            Qt.callLater(root.refreshLanguage)
        }
    }

    Process {
        id: statusProc
        command: ["/usr/bin/python3", "-I", root.helperPath, "status"]
        stdout: StdioCollector { onStreamFinished: root.ingest(text) }
    }
    Process {
        id: actionProc
        stdout: StdioCollector { onStreamFinished: if (text.trim() !== "") root.ingest(text) }
        stderr: StdioCollector { onStreamFinished: if (text.trim() !== "") root.actionError = text.trim().slice(0, 300) }
        onExited: (code, status) => {
            if (code !== 0) {
                root.requestedMode = ""
                if (!root.actionError) root.actionError = "Couldn't save keyboard settings"
            }
            if (root.pendingUpdate !== null) {
                var update = root.pendingUpdate
                root.pendingUpdate = null
                Qt.callLater(() => root.submit(update))
            } else {
                Qt.callLater(root.refresh)
                Qt.callLater(root.refreshPeers)
            }
        }
    }

    Ui.WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: " " + (root.language.label || "EN")
        fontSize: Style.font.bodySmall
        tooltipText: root.language.name + " · Corsair keyboard\n" + (root.canSwitchLayout ? "Middle-click: next layout · " : "") + "Right-click: theme · Wheel: lighting"
        onPressed: b => {
            if (b === Qt.RightButton) root.submit({mode: "theme"})
            else if (b === Qt.MiddleButton) { if (root.canSwitchLayout) root.switchLanguage("toggle") }
            else root.toggle()
        }
        onWheelMoved: delta => { if (delta !== 0) root.cycle(delta < 0 ? 1 : -1) }
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: button
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: content
        contentWidth: fittedContentWidth(Style.space(420))
        contentHeight: fittedContentHeight(column.implicitHeight)

        Item {
            id: content
            anchors.fill: parent
            focus: true
            Keys.onEscapePressed: root.close()
            Keys.onLeftPressed: root.cycle(-1)
            Keys.onRightPressed: root.cycle(1)

            Flickable {
                anchors.fill: parent
                contentWidth: width
                contentHeight: column.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: column
                    width: parent.width
                    spacing: Style.space(12)

                    Ui.PanelHero {
                        title: "Corsair K65 Plus"
                        meta: root.device.error ? root.device.error : (root.device.connected ? "Wired · " + (root.device.mode || root.config.mode) : "Keyboard disconnected")
                        detail: root.language.label || "EN"
                    }

                    Grid {
                        id: layoutGrid
                        width: parent.width
                        visible: root.canSwitchLayout
                        // Up to four per row; names are only spelled out while the buttons are wide.
                        columns: Math.max(1, Math.min(root.layoutChoices.length, root.layoutChoices.length > 2 ? 4 : 2))
                        spacing: Style.space(6)
                        Repeater {
                            model: root.layoutChoices
                            Ui.Button {
                                required property var modelData
                                width: (layoutGrid.width - layoutGrid.spacing * (layoutGrid.columns - 1)) / layoutGrid.columns
                                text: root.layoutChoices.length > 2 || modelData.name.length > 16 ? modelData.label : modelData.label + " · " + modelData.name
                                tooltipText: modelData.name
                                selected: root.language.active === modelData.code
                                enabled: !languageAction.running
                                bordered: true
                                focusable: true
                                onClicked: root.switchLanguage(modelData.code)
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        visible: root.languageError !== "" || root.layoutChoices.length > 0
                        text: root.languageError || (root.canSwitchLayout
                            ? "Ctrl+Alt+Space or middle-click the bar icon to switch layout"
                            : "Only one keyboard layout is configured. Add more, for example kb_layout = \"us,de\" in ~/.config/hypr/input.lua, to switch here.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.languageError ? "#ff7070" : Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        opacity: root.languageError ? 1 : 0.55
                    }

                    Rectangle {
                        id: gallery
                        width: parent.width
                        height: galleryColumn.implicitHeight + Style.space(24)
                        color: Color.background
                        border.width: 1
                        border.color: Qt.darker(Color.foreground, 3)
                        radius: Style.cornerRadius
                        activeFocusOnTab: true
                        Keys.onLeftPressed: root.cycle(-1)
                        Keys.onRightPressed: root.cycle(1)
                        Keys.onUpPressed: root.cycle(-1)
                        Keys.onDownPressed: root.cycle(1)

                        Column {
                            id: galleryColumn
                            x: Style.space(12)
                            y: Style.space(12)
                            width: parent.width - Style.space(24)
                            spacing: Style.space(10)
                            Row {
                                width: parent.width
                                spacing: Style.space(8)
                                Ui.Button {
                                    width: Style.space(30)
                                    text: "‹"
                                    fontSize: Style.font.title
                                    focusable: true
                                    onClicked: root.cycle(-1)
                                }
                                Column {
                                    width: parent.width - Style.space(76)
                                    spacing: Style.space(2)
                                    Text {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        text: root.currentLook.name
                                        color: Color.foreground
                                        font.family: Style.font.family
                                        font.pixelSize: Style.font.title
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        text: (root.currentLook.animated ? "● Motion" : root.currentLook.category) + " · " + (root.modeIndex + 1) + " / " + root.modes.length
                                        color: Color.foreground
                                        opacity: 0.6
                                        font.family: Style.font.family
                                        font.pixelSize: Style.font.bodySmall
                                    }
                                }
                                Ui.Button {
                                    width: Style.space(30)
                                    text: "›"
                                    fontSize: Style.font.title
                                    focusable: true
                                    onClicked: root.cycle(1)
                                }
                            }
                            Column {
                                width: parent.width
                                spacing: Style.space(3)
                                Repeater {
                                    model: root.previewRows
                                    Row {
                                        required property var modelData
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        spacing: Style.space(3)
                                        Repeater {
                                            model: modelData
                                            Rectangle {
                                                required property string modelData
                                                width: (galleryColumn.width - Style.space(42)) / 15
                                                height: Style.space(8)
                                                radius: Style.space(2)
                                                color: modelData
                                                Behavior on color { ColorAnimation { duration: 250 } }
                                            }
                                        }
                                    }
                                }
                            }
                            Text {
                                width: parent.width
                                text: root.currentLook.hint
                                wrapMode: Text.WordWrap
                                horizontalAlignment: Text.AlignHCenter
                                color: Color.foreground
                                font.family: Style.font.family
                                font.pixelSize: Style.font.bodySmall
                                opacity: 0.8
                            }
                            Text {
                                width: parent.width
                                text: "Scroll to explore · arrow keys work too"
                                horizontalAlignment: Text.AlignHCenter
                                color: Color.foreground
                                font.family: Style.font.family
                                font.pixelSize: Style.font.bodySmall
                                opacity: 0.45
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.NoButton
                            onWheel: wheel => {
                                if (wheel.angleDelta.y !== 0) root.cycle(wheel.angleDelta.y < 0 ? 1 : -1)
                                wheel.accepted = true
                            }
                        }
                    }
                    Row {
                        width: parent.width
                        spacing: Style.space(6)
                        Ui.Button {
                            width: (parent.width - parent.spacing) / 2
                            text: root.galleryExpanded ? "Hide gallery" : "Browse all " + root.modes.length + " looks"
                            bordered: true
                            focusable: true
                            onClicked: root.galleryExpanded = !root.galleryExpanded
                        }
                        Ui.Button {
                            width: (parent.width - parent.spacing) / 2
                            text: "Surprise me"
                            bordered: true
                            focusable: true
                            onClicked: root.surprise()
                        }
                    }
                    Column {
                        width: parent.width
                        spacing: Style.space(6)
                        visible: root.galleryExpanded
                        Row {
                            width: parent.width
                            spacing: Style.space(4)
                            Repeater {
                                model: ["All", "Palettes", "Motion", "Custom"]
                                Ui.Button {
                                    required property string modelData
                                    width: (parent.width - parent.spacing * 3) / 4
                                    text: modelData
                                    selected: root.category === modelData
                                    focusable: true
                                    onClicked: root.category = modelData
                                }
                            }
                        }
                        Grid {
                            width: parent.width
                            columns: 2
                            spacing: Style.space(4)
                            Repeater {
                                model: root.browseModes
                                Ui.Button {
                                    required property var modelData
                                    width: (parent.width - parent.spacing) / 2
                                    text: modelData.name
                                    fontSize: Style.font.bodySmall
                                    tooltipText: modelData.hint
                                    selected: root.selectedMode === modelData.id
                                    bordered: true
                                    focusable: true
                                    onClicked: root.submit({mode: modelData.id})
                                }
                            }
                        }
                    }

                    Text {
                        text: "QUICK COLORS"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        opacity: 0.65
                    }
                    Grid {
                        width: parent.width
                        columns: 10
                        spacing: Style.space(4)
                        Repeater {
                            model: root.colors
                            Ui.Button {
                                required property var modelData
                                width: (parent.width - parent.spacing * 9) / 10
                                text: "●"
                                fontSize: Style.font.title
                                foreground: "#" + modelData.hex
                                tooltipText: modelData.name + " · #" + modelData.hex.toUpperCase()
                                selected: root.config.mode === "solid" && root.config.color === modelData.hex
                                bordered: true
                                focusable: true
                                enabled: !actionProc.running
                                onClicked: root.submit({mode: "solid", color: modelData.hex})
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: Style.space(8)
                        visible: root.currentLook.custom === true
                        Column {
                            width: (parent.width - parent.spacing) / 2
                            spacing: Style.space(4)
                            Text {
                                text: "Base color"
                                color: Color.foreground
                                font.family: Style.font.family
                                font.pixelSize: Style.font.bodySmall
                            }
                            Ui.TextField {
                                id: baseField
                                width: parent.width
                                text: "#00aaff"
                                placeholderText: "#00AAFF"
                                maximumLength: 7
                                selectByMouse: true
                                onTextEdited: root.baseColorDirty = true
                                onAccepted: root.applyCustom()
                            }
                        }
                        Column {
                            width: (parent.width - parent.spacing) / 2
                            spacing: Style.space(4)
                            Text {
                                text: "Accent color"
                                color: Color.foreground
                                font.family: Style.font.family
                                font.pixelSize: Style.font.bodySmall
                            }
                            Ui.TextField {
                                id: accentField
                                width: parent.width
                                text: "#ff4080"
                                placeholderText: "#FF4080"
                                maximumLength: 7
                                selectByMouse: true
                                onTextEdited: root.accentColorDirty = true
                                onAccepted: root.applyCustom()
                            }
                        }
                    }
                    Ui.Button {
                        width: parent.width
                        visible: root.currentLook.custom === true
                        text: root.selectedMode === "solid" || root.selectedMode === "breathe" ? "Apply base color" : "Apply both colors"
                        bordered: true
                        focusable: true
                        enabled: !actionProc.running
                        onClicked: root.applyCustom()
                    }

                    Column {
                        width: parent.width
                        spacing: Style.space(6)
                        visible: root.currentLook.animated === true
                        Text {
                            text: "MOTION SPEED · " + root.config.speed + "%"
                            color: Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                        }
                        Ui.PanelSlider {
                            width: parent.width
                            bar: root.bar
                            minimum: 10
                            maximum: 100
                            integer: true
                            step: 5
                            value: root.config.speed
                            onReleased: value => root.submit({speed: Math.round(value)})
                        }
                        Row {
                            width: parent.width
                            spacing: Style.space(6)
                            Repeater {
                                model: [{name: "Dreamy", value: 20}, {name: "Flow", value: 50}, {name: "Energetic", value: 90}]
                                Ui.Button {
                                    required property var modelData
                                    width: (parent.width - parent.spacing * 2) / 3
                                    text: modelData.name
                                    selected: root.config.speed === modelData.value
                                    focusable: true
                                    onClicked: root.submit({speed: modelData.value})
                                }
                            }
                        }
                    }

                    Text {
                        text: "BRIGHTNESS · " + root.config.brightness + "%"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        opacity: root.config.mode === "hardware" ? 0.4 : 1
                    }
                    Ui.PanelSlider {
                        width: parent.width
                        bar: root.bar
                        minimum: 0
                        maximum: 100
                        integer: true
                        step: 5
                        value: root.config.brightness
                        enabled: root.config.mode !== "hardware" && !actionProc.running
                        onReleased: value => root.submit({brightness: Math.round(value)})
                    }
                    Row {
                        width: parent.width
                        spacing: Style.space(6)
                        Repeater {
                            model: [25, 50, 75, 100]
                            Ui.Button {
                                required property int modelData
                                width: (parent.width - parent.spacing * 3) / 4
                                text: modelData + "%"
                                selected: root.config.brightness === modelData
                                focusable: true
                                enabled: root.config.mode !== "hardware" && !actionProc.running
                                onClicked: root.submit({brightness: modelData})
                            }
                        }
                    }
                    Ui.Button {
                        width: parent.width
                        visible: root.config.mode === "theme"
                        text: root.config.vivid ? "Theme colors: vivid LEDs" : "Theme colors: exact RGB"
                        tooltipText: "Click to toggle LED-friendly color adjustment"
                        focusable: true
                        bordered: true
                        enabled: !actionProc.running
                        onClicked: root.submit({vivid: !root.config.vivid})
                    }
                    Row {
                        width: parent.width
                        spacing: Style.space(4)
                        Repeater {
                            model: [{id: "theme", name: "Theme sync"}, {id: "off", name: "Off"}, {id: "hardware", name: "Built-in"}]
                            Ui.Button {
                                required property var modelData
                                width: (parent.width - parent.spacing * 2) / 3
                                text: modelData.name
                                selected: root.selectedMode === modelData.id
                                focusable: true
                                bordered: true
                                onClicked: root.submit({mode: modelData.id})
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        text: root.actionError || "Choices are saved. Right-click the bar icon to resume theme sync."
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.actionError ? "#ff7070" : Color.foreground
                        opacity: root.actionError ? 1 : 0.6
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                    }
                }
            }
        }
    }
}
