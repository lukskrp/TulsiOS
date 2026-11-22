/* The slides shown while TulsiOS installs. */
import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    function nextSlide() {
        presentation.goToNextSlide();
    }

    Timer {
        interval: 15000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: nextSlide()
    }

    component TulsiSlide: Slide {
        property string heading
        property string body
        Image {
            id: logo
            source: "logo.svg"
            width: 120; height: 120
            // Render the vector at twice the drawn size, so it stays sharp on HiDPI.
            sourceSize: Qt.size(240, 240)
            smooth: true
            fillMode: Image.PreserveAspectFit
            anchors.bottom: title.top
            anchors.bottomMargin: 20
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            id: title
            anchors.centerIn: parent
            text: heading
            font.pixelSize: 28
            color: "#3f8a4f"
            width: presentation.width
            horizontalAlignment: Text.Center
            wrapMode: Text.WordWrap
        }
        Text {
            anchors.top: title.bottom
            anchors.topMargin: 12
            anchors.horizontalCenter: parent.horizontalCenter
            text: body
            width: presentation.width * 0.8
            horizontalAlignment: Text.Center
            wrapMode: Text.WordWrap
        }
    }

    TulsiSlide {
        heading: "Software, the easy way"
        body: "Find and install programs in the <b>Software Center</b>. Everything you install is "
            + "written down, so your system can always be rebuilt exactly as it is."
    }

    TulsiSlide {
        heading: "Ask the Assistant"
        body: "Press <b>Super+A</b> and ask in your own words: \"install a video editor\", "
            + "\"turn on printing\". You decide how much the Assistant may do on its own."
    }

    TulsiSlide {
        heading: "Every change can be undone"
        body: "The <b>History</b> page lists every change, by you or the Assistant, with an Undo "
            + "button. If something breaks, pick an earlier version when the computer starts."
    }

    TulsiSlide {
        heading: "Your choice of desktop"
        body: "Ocimum Desktop for a classic panel and start menu, or dwm for keyboard-driven "
            + "tiling. Switch later with one line in /etc/nixos/configuration.nix."
    }

    function onActivate() { }
    function onLeave() { }
}
