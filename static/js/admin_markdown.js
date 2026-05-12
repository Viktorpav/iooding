document.addEventListener('DOMContentLoaded', function() {
    var bodyField = document.getElementById('id_body');
    if (bodyField) {
        var easyMDE = new EasyMDE({
            element: bodyField,
            spellChecker: false,
            autosave: {
                enabled: true,
                uniqueId: "PostContent",
                delay: 1000,
            },
            status: ["autosave", "lines", "words", "cursor"],
            renderingConfig: {
                singleLineBreaks: false,
                codeSyntaxHighlighting: true,
            },
            minHeight: "400px",
            sideBySideFullscreen: false,
        });
    }
});
