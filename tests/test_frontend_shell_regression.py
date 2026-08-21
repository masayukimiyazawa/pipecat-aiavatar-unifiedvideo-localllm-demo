"""Regression guard for frontend-shell 2.2 — subscriber container."""

def test_subscriber_container_hidden_and_no_child_video_rule():
    html = open("static/index.html").read()
    # Parent must remain hidden
    assert 'id="subscriberContainer"' in html
    assert 'style="display:none"' in html, "parent #subscriberContainer must have display:none"
    # Child video rule must be removed (replaced with comment)
    assert "#subscriberContainer video { max-width" not in html
    assert "#subscriberContainer video {max-width" not in html
    # Comment replacement must exist
    assert "child video rule removed as redundant" in html
    # No display:none for video child
    # Ensure no stray display:none for video inside subscriberContainer
    import re
    # Find all occurrences of "#subscriberContainer video"
    matches = re.findall(r"#subscriberContainer\s+video", html)
    assert len(matches) == 0, f"found redundant child rule: {matches}"
