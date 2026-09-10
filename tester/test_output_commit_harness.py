from pipeline.helpers import StreamingTagFilter
from pipeline.lixsearch import _may_stream_uncommitted_output


def test_reasoning_tags_split_across_chunks_never_reach_sse_text():
    filter_ = StreamingTagFilter()
    chunks = ["<thi", "nking>private plan", "</think", "ing>Final answer"]
    visible = "".join(filter_.feed(chunk) for chunk in chunks) + filter_.flush()
    assert visible == "Final answer"


def test_unclosed_reasoning_block_is_discarded_on_flush():
    filter_ = StreamingTagFilter()
    visible = filter_.feed("<analysis>private plan") + filter_.flush()
    assert visible == ""


def test_artifact_draft_is_buffered_until_commit():
    assert _may_stream_uncommitted_output(
        "event-id", has_tools=False, artifact_requested=True
    ) is False


def test_plain_final_answer_can_stream_after_tool_boundary_is_clear():
    assert _may_stream_uncommitted_output(
        "event-id", has_tools=False, artifact_requested=False
    ) is True
    assert _may_stream_uncommitted_output(
        "event-id", has_tools=True, artifact_requested=False
    ) is False
