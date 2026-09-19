from dataclasses import dataclass, field

from app.schemas import (
    AssistantTurn,
    ConfirmationAnswer,
    QuestionResponse,
    SlotUpdate,
    YesNoAnswer,
)
from app.services.conversation import ConversationService


@dataclass
class ScriptedLLM:
    """Returns canned responses in call order, tracking every prompt seen."""

    prompts: list = field(default_factory=list)

    async def complete(self, *, system_prompt, history, response_model):
        self.prompts.append(system_prompt)

        if response_model is QuestionResponse:
            return QuestionResponse(question="canned question")

        if response_model is YesNoAnswer:
            return YesNoAnswer(yes=True)

        if response_model is ConfirmationAnswer:
            return ConfirmationAnswer(confirmed=True)

        # AssistantTurn (main slot-filling turn)
        return AssistantTurn(
            updated_fields=SlotUpdate(
                category="paani",
                ministry="Drinking Water and Sanitation",
                description="gali mein paani ki paipi phati hai",
                location="gandhi chowk",
                date="aaj",
                name="ramesh",
                contact="9876543210",
            ),
            next_question="kya aap abhi usi jagah par hain?",
        )


def _svc() -> tuple[ConversationService, ScriptedLLM, str]:
    llm = ScriptedLLM()
    svc = ConversationService(llm)
    sid = svc.create_session("t1").session_id
    return svc, llm, sid


async def test_flow_reaches_confirming_after_evidence_and_assist():
    svc, llm, sid = _svc()
    await svc.start(sid)

    # One turn fills all required fields -> should enter evidence stage.
    r = await svc.process_turn(sid, "meri gali mein paani ki paipi phati hai")
    assert r.status == "evidence"
    assert r.question == "canned question"
    assert not r.request_evidence

    # LLM says yes (has evidence) -> request attach.
    r = await svc.process_turn(sid, "haan, mere paas photo hai")
    assert r.status == "evidence"
    assert r.request_evidence is True

    # App uploads and replies with the [EVIDENCE:] marker -> moves to assist.
    r = await svc.process_turn(sid, "[EVIDENCE: a1b2c3d4_photo.pdf]")
    assert r.status == "assist"
    assert svc.get(sid).slots.get("evidence_file") == "a1b2c3d4_photo.pdf"
    assert svc.get(sid).slots.get("evidence") == "yes"

    # LLM judge says yes (needs help) -> still reaches confirming.
    r = await svc.process_turn(sid, "haan, mujhe madad chahiye")
    assert r.status == "confirming"
    assert r.report_text
    assert r.question  # confirmation yes/no question from the LLM

    # Confirm.
    r = await svc.process_turn(sid, "haan")
    assert r.status == "done"


async def test_evidence_no_skips_attach():
    svc, llm, sid = _svc()
    await svc.start(sid)
    r = await svc.process_turn(sid, "meri gali mein paani ki paipi phati hai")
    assert r.status == "evidence"

    # Judge always returns yes in this script; simulate no by monkeypatching.
    async def no(*, system_prompt, history, response_model):
        if response_model is YesNoAnswer:
            return YesNoAnswer(yes=False)
        if response_model is QuestionResponse:
            return QuestionResponse(question="canned question")
        return AssistantTurn(
            updated_fields=SlotUpdate(
                category="paani",
                ministry="Drinking Water and Sanitation",
                description="gali mein paani ki paipi phati hai",
                location="gandhi chowk",
                date="aaj",
                name="ramesh",
                contact="9876543210",
            ),
            next_question="kya yeh report sahi hai?",
        )

    svc._llm.complete = no
    r = await svc.process_turn(sid, "nahi, koi document nahi hai")
    assert r.status == "assist"
    assert svc.get(sid).slots.get("evidence") == "no"
    assert svc.get(sid).slots.get("evidence_file") is None