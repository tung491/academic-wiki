To: @karpathy and @torvalds and all participants

Proposed Comment for Gist Discussion
Git object model as a knowledge backend — why reinvent the wheel?
Going through the 485+ comments, I see a recurring pattern: we are all building custom infrastructure for graph databases, SPARQL, entity stores, and lint pipelines from scratch. But we already have a battle-tested, content-addressable storage with deduplication, provenance, and branching built-in: Git internals.

Instead of just storing Markdown files, why not map knowledge units directly to the Git object model?

The Mapping:

Blob → Atomic knowledge unit (a single fact, a proven pattern, or even a "rejected approach").
Tree → Category/Index (a directory of related concepts or a specific context snapshot).
Commit → Provenance event (who added what, when, and why — with a clear message/reasoning).
Branch → Competing hypotheses or parallel research threads (keeping uncertainty alive until evidence resolves it).
Merge → Synthesis or resolution (one interpretation wins, or they are merged into a unified truth).
Tag → Stable knowledge snapshot ("verified/audited as of date X").
What this gives us for free:

Content Deduplication: Same knowledge = same SHA. This prevents "LLM agents" vs "AI agents" duplicates from bloating the context.
Immutable Provenance: Every fact knows its origin. No more "mostly correct" JSON failures that are hard to trace.
Anti-Repetition Memory: Failed experiments stored as typed blobs. The agent can query "what didn't work" before wasting tokens trying it again.
Diff-based Reviews: A clean way to see exactly how the knowledge state evolved between agent iterations.
The Open Challenge: Active Recall
The biggest gap remains: "How does the agent know to look for something it forgot it has?" Even with a perfect Git-based index, triggering retrieval during a conversation without hardcoded triggers is still the "holy grail." Semantic hashes and tags help, but the "I didn't know I should search" problem is still open.

Pragmatic Take:
Current Markdown + vector search covers ~90% of use cases for ~10% of the effort. But when we hit the walls of scale, deduplication, and provenance, the Git object model becomes a very compelling "knowledge plumbing" solution.

Would love to hear if anyone is already experimenting with using git plumbing commands (not just the porcelain) as their agent's memory backend!