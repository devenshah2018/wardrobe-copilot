import time

from .recommendations import ModelError, validate_outfits
from .schemas import Constraints, Proposal


CASES = [
    ("casual", "Casual", "Give me three casual outfits.", None),
    ("business", "Business casual", "Give me three business-casual outfits.", None),
    ("formal", "Formal", "Give me three formal outfits.", None),
    ("athletic", "Athletic", "Give me three athletic outfits.", None),
    ("warm", "Warm day", "Give me three outfits for a warm day.", None),
    ("weekend", "Weekend", "Give me three relaxed weekend outfits.", None),
    ("no-trousers", "Exclude trousers", "Give me three casual outfits without trousers.", None),
    ("no-black", "Exclude black", "Give me three business-casual outfits without black clothing.", None),
    ("casual-followup", "Casual refinement", "Make option 2 more casual.", "business"),
    ("formal-followup", "Formal refinement", "Make option 1 a little more formal.", "casual"),
]


def run_suite(stylist, items, save_progress, result):
    conversations = {}
    for case_id, label, prompt, follow_up_to in CASES:
        conversation = conversations.get(follow_up_to) if follow_up_to else None
        if conversation is None:
            conversation = {"messages": [], "constraints": {}}
        started = time.monotonic()
        error = None
        reply = {"message": "", "outfits": []}
        constraints = conversation["constraints"]
        try:
            reply, constraints = stylist.recommend(prompt, items, conversation)
            checked, validation_errors = validate_outfits(
                Proposal.model_validate(reply), items,
                Constraints.model_validate(constraints),
            )
            if validation_errors or len(checked) != len(reply["outfits"]):
                error = "The recommendation did not pass outfit validation."
                reply["outfits"] = checked
        except (ModelError, ValueError) as problem:
            error = str(problem)
        duration = round(time.monotonic() - started, 2)
        outfits = reply["outfits"]
        result["cases"].append(
            {
                "id": case_id,
                "label": label,
                "prompt": prompt,
                "follow_up_to": follow_up_to,
                "seconds": duration,
                "outfit_count": len(outfits),
                "partial_count": sum(
                    bool(outfit["missing_components"]) for outfit in outfits
                ),
                "distinct_count": len(
                    {tuple(sorted(outfit["item_ids"])) for outfit in outfits}
                ),
                "message": reply["message"],
                "outfits": outfits,
                "error": error,
            }
        )
        conversation = {
            "constraints": constraints,
            "messages": conversation["messages"] + [
                {"role": "user", "text": prompt, "outfits": []},
                {"role": "assistant", "text": reply["message"], "outfits": outfits},
            ],
        }
        conversations[case_id] = conversation
        save_progress(result)
    result["status"] = "complete"
    save_progress(result)
