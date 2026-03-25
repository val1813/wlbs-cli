# World-Line Behavior Space: A Unified Framework for Continual Learning and Spatial Root-Cause Attribution in AI-Driven Autonomous Systems

**Zhongchang Huang (黄中常)**
Independent Researcher, Nanjing, Jiangsu, China
Email: valhuang@kaiwucl.com

*Preprint — arXiv:cs.SE / cs.AI · March 25, 2026*
*CN Patent Applications: 2026103746505 · 2026103756225*
## Abstract
We present the World-Line Behavior Space (WLBS) framework, a novel architecture for continual learning and spatial root-cause attribution in AI-driven autonomous systems. WLBS abstracts the operational history of any system component as a world-line — a complete spatiotemporal trajectory inspired by the Minkowski spacetime formalism — that is structurally accessible as an append-only sequence without requiring retrieval. Combined with the Aporia mechanism, which propagates failure signals backward along dependency graphs with exponential decay (analogous to gradient propagation in convolutional neural networks, though not mathematically equivalent), WLBS enables precise cross-file and cross-module root-cause localization without natural language translation. A resolution-decay context assembly mechanism, inspired by the biological fovea, organizes historical information by behavioral distance to maximize information density within bounded context windows. Preliminary experiments on a software repair task demonstrate correct cross-file root-cause identification (roles.py→rbac.py behavioral distance = 1 hop) and behavior graph construction within 6–26 ms. Full benchmark evaluation is ongoing. We discuss the generalizability of WLBS beyond software engineering to microservice fault diagnosis, supply chain risk propagation, medical symptom attribution, and large language model training paradigms.

## 1.  Introduction
Consider a concrete failure mode. A software repair agent observes an ImportError in rbac.py and edits rbac.py — three times, ten times — without success. The actual bug is in roles.py, which rbac.py imports. The error manifests downstream; the cause lives upstream. The agent has no mechanism to look upstream, because its history of failed attempts is stored as natural language summaries, not as a map of the dependency graph it is operating on.
This is not an edge case. Cross-file root causes are common in real codebases, and they expose a systematic gap in how current AI repair systems handle memory. Systems such as SWE-agent [Yang et al., 2024] and the broader class of RAG-augmented agents [Lewis et al., 2020; Shinn et al., 2023] store experience as text: rules extracted from prior runs, reflections on past failures, retrieved code snippets. The structural information — which function called which, how failure signals propagate through a call graph — does not survive this translation. What remains is temporal (this failed before) rather than spatial (this failed because of something upstream).
> **Figure 1 shows the contrast directly. Left: an existing system records failures temporally and targets the wrong file. Right: the WLBS framework records failures spatially — as curvature increments on nodes in the dependency graph — and surfaces the true root cause automatically.**

> **Figure 1. Existing approach (left) versus WLBS (right) on a cross-file root-cause scenario. Curvature values κ accumulate through dependency-graph propagation, surfacing the true root cause without natural language translation.**
Three problems follow from this architecture. When a test fails, the failure message names the symptom file, not the cause. Compressing this into a rule — 'watch out for import errors in rbac.py' — discards the call-graph context that would point to roles.py. The spatial signal is destroyed at the first transcoding step.
Even if the rule survived, it would describe a past event in time, not a position in the dependency graph. The agent needs to know: is this file a cause or a symptom? A timeline of failures cannot answer that question. What is needed is a map.
Third: when the agent finally finds the right file and fixes it, the reasoning that led there — why roles.py rather than rbac.py — disappears. The next run starts over. Each task is an island. There is no mechanism for the system's diagnostic reasoning to compound across repeated encounters with similar code structures.
The World-Line Behavior Space (WLBS) framework is built around a different data model: rather than distilling experience into rules, it keeps experience in place. Each node in the dependency graph — each function, class, or module — carries an append-only log of every execution event involving that node, across all tasks. This log is called a world-line. It is not retrieved; it is structurally present.
Four mechanisms operate on this data model:
- Each world-line entry records not just the outcome (pass/fail, test delta) but the reasoning process that led to that action and whether the reasoning was correct. The system accumulates a map of its own past mistakes.
- When a test fails, a curvature increment propagates backward along the dependency graph with exponential decay proportional to call-chain distance. After several failed tasks involving the same cross-file dependency, the upstream root cause accumulates the highest curvature — and is flagged as a singularity.
- Context is assembled by behavioral distance from the current task. Nearby nodes receive their full world-line; distant nodes contribute only their identifier and curvature value. This respects the context budget without discarding structural information.
- The singularity flag is a typed attribute on the graph node, not a natural language warning. The decision layer reads it directly. No translation step, no parsing uncertainty.
We implement WLBS in OpenCraft. On a cross-file repair benchmark (b-16: roles.py → rbac.py), the system correctly identifies the upstream root cause and routes to it stably across ten turns, with gate failure rate below 5%. Behavior graph construction takes 5–22 ms. Full benchmark evaluation is ongoing.
The same data model — append-only event logs on dependency graph nodes, curvature propagation along edges — applies wherever systems have structured dependencies and repeated failure signals: microservice call graphs [Mnih et al., 2015], supply chain networks, and, as a speculative long-term direction, training pipelines for large language models [Parisi et al., 2019; Wang et al., 2023; Kirkpatrick et al., 2017] in which inference-time memory accumulation might complement parameter updates.
The technical contributions described in this paper are protected under CN Patent Applications 2026103746505 and 2026103756225, both filed March 25, 2026.
## 2.  Related Work
### 2.1  AI-Assisted Code Repair
Recent systems such as Claude Code [Anthropic, 2024], GitHub Copilot [Chen et al., 2021], and Cursor [Anysphere, 2024] demonstrate strong performance on isolated coding tasks but lack persistent cross-task memory. SWE-bench [Jimenez et al., 2023] establishes evaluation standards for software engineering agents but does not address the cross-file root-cause problem that motivates WLBS.
### 2.2  Continual Learning
The continual learning literature [Parisi et al., 2019; Kirkpatrick et al., 2017] primarily addresses catastrophic forgetting in neural network parameters. WLBS takes a different approach: rather than preventing forgetting in parameters, it makes forgetting a deliberate design choice rather than an emergent failure, by preserving operational trajectories as append-only world-lines. We note that the resolution decay mechanism does introduce a form of lossy compression for distant history — this is an intentional trade-off, not a claim of lossless infinite memory.
### 2.3  Fault Localization
Spectrum-based fault localization [Jones et al., 2002] and mutation testing [Jia and Harman, 2011] identify suspicious code locations from test coverage data. These methods operate in the time dimension rather than the space dimension. WLBS's curvature propagation adds spatial attribution along the dependency graph.
### 2.4  Retrieval-Augmented Generation
RAG systems [Lewis et al., 2020] augment language model inference with retrieved documents. WLBS differs fundamentally: where RAG retrieves documents and injects them as text, WLBS makes the behavioral graph structurally present as typed data. There is no retrieval step and no natural language translation of structural information.
### 2.5  Reflection and Reasoning Loops
Reflexion [Shinn et al., 2023] reinforces language agents through linguistic feedback stored in an episodic memory buffer. WLBS differs in that reasoning history is stored as structured events in the world-line alongside execution outcomes, persisting across tasks rather than within a single episode.
## 3.  The World-Line Behavior Space Framework
### 3.1  Core Definitions
Definition 1 (Behavior Node). A behavior node n ∈ N is a function, class, or module characterized by its identifier, file location, outgoing call edges calls(n), incoming call edges called_by(n), and real-time curvature κ(n) ∈ ℝ≥0.
Definition 2 (Behavioral Distance). The behavioral distance d(n₁, n₂) is the shortest call-chain hop count in the behavior graph. Nodes in disconnected components have d = ∞.
Definition 3 (World-Line). The world-line W(n) of node n is an append-only sequence of events {e₁, e₂, ..., eₜ}. Each event records: task identifier, action type, execution result, test-pass delta δ, gate reasoning process, and was_correct flag.
Definition 4 (Singularity). A node n is a singularity if and only if: (a) κ(n) > θ for threshold θ; (b) at least two historical test failures appear in downstream nodes reachable via calls(n); and (c) n has no direct test failure record. Condition (c) distinguishes singularities from ordinary high-curvature nodes.
### 3.2  Curvature Propagation
When a test fails at node nf, curvature propagates upstream:
Δκ(n) = α · λ^d(n, nf)
where α is the base increment (default 0.1), λ is the decay coefficient (default 0.5), and d(n, nf) is the behavioral distance from node n to the failure node. Nodes closer to the root cause accumulate larger curvature increments.
When a test succeeds:
κ(n) ← κ(n) · γ,  where γ < 1  (default 0.9)
This mechanism requires no neural computation — it is pure rule-based arithmetic executable in O(|E|) time where |E| is the number of edges in the behavior graph.
### 3.3  Resolution Decay Context Assembly
Historical information is organized into three tiers by behavioral distance:


This mechanism, inspired by the biological fovea, ensures that the most relevant historical information receives full fidelity while distant information contributes structural context without consuming excessive context budget.
### 3.4  Reasoning Feedback Loop
Each Gate decision records its reasoning process (gate_reasoning) and outcome (was_correct) in the corresponding node's world-line. When the same node is encountered in a future task, the decision layer observes previous reasoning failures and corrects its inference direction without parameter updates. This differs from Reflexion [Shinn et al., 2023] in that reasoning history persists as structured events across tasks rather than as natural language in an episodic buffer.
## 4.  System Architecture: OpenCraft
We implement WLBS in OpenCraft. The system comprises five modules:
- BehaviorGraph: Maintains the function-level behavior graph, world-line structures, and node curvature. Constructed via AST static analysis augmented by runtime tracing (sys.settrace). Supports incremental growth without full reconstruction.
- ResolutionLayer: Implements three-tier resolution decay context assembly by behavioral distance.
- Aporia: Implements singularity detection using the three-condition criterion (Definition 4). Marks singularity nodes with a structured boolean attribute directly in the behavior graph, bypassing natural language description.
- Gate: A large language model serving as the projection operator. Receives the behavior graph cross-section as structured data and outputs decision instructions including target node, action type, and reasoning process.
- Expert + Update: Executes Gate decisions, obtains test feedback, appends execution events to world-lines, and updates behavior graph curvature.
## 5.  Preliminary Evaluation
### 5.1  Experimental Setup
We evaluate OpenCraft on a set of Python software repair tasks. We compare two configurations:
- Baseline (A): Original architecture with rule injection via living state, active_understanding, and Aporia boundary_note text generation.
- WLBS (B): Behavior graph context replacement with curvature propagation, resolution decay assembly, and Gate whitelist fields.
### 5.2  Verified Results
The following results are directly measured from the OpenCraft implementation. All spatial attribution results refer to a single cross-file dependency case (b-16: roles.py→rbac.py, 1-hop). Generalizability to other cross-file scenarios requires full benchmark evaluation across diverse task types.


### 5.3  Limitations and Ongoing Work
In our current OpenCraft implementation, we verified that the roles.py→rbac.py behavioral distance in the b-16 cross-file repair task is exactly one hop. Routing-context construction times were measured between 5.27 ms and 21.67 ms on three benchmark tasks. The Gate's WLBS-style routing prompt for b-16 remained compact at approximately 375 tokens while selecting roles.py as the first effective write target. In online execution, the system improved b-16 to 42/44 passing tests under a valid run configuration (gate failure rate 4.76%), with improvement from 34/44 to 42/44 observed across engineering iterations. Full completion and large-scale benchmark comparison remain ongoing; provider stability issues have prevented clean A/B evaluation at scale.
## 6.  Beyond Software Engineering: Generalization of WLBS
The following applications are proposed as potential future research directions. None have been experimentally validated in this paper; they are presented to illustrate the generalizability of the WLBS framework as a hypothesis for future investigation. The three requirements for applicability are: (1) the system has a dependency structure representable as a directed graph; (2) failure signals can be detected and attributed to nodes; (3) repeated tasks occur over time.
### 6.1  Microservice Fault Diagnosis
In microservice architectures, behavior nodes are service instances, call edges are API dependencies, and failures are health check timeouts. Curvature propagation along service call chains identifies upstream root-cause services from downstream failure manifestations — addressing a gap in current observability tools (Jaeger, Zipkin, Datadog) which correlate traces temporally but do not perform spatial attribution along dependency graphs.
### 6.2  Supply Chain Risk Propagation
Supply chain networks are dependency graphs where nodes are suppliers, edges are supply relationships, and failure events are disruptions. Curvature propagation identifies upstream critical fragile points whose disruption propagates most strongly through the network. Singularity nodes in a supply chain are structural single points of failure discovered automatically through operational history.
### 6.3  Clinical Symptom Attribution
In clinical diagnosis, nodes are physiological systems, edges are known causal relationships, and failures are abnormal test results. Curvature propagation along physiological dependency graphs could surface root-cause conditions from downstream symptom manifestations. We emphasize that this application requires rigorous clinical validation and must serve only as decision support, not diagnosis replacement.
### 6.4  Large Language Model Training
The most ambitious generalization of WLBS is toward test-time continual learning for large language models. We propose that world-lines can serve as inference-time memory: rather than accumulating task-specific experience through parameter updates (fine-tuning, RLHF), a model reads its own accumulated reasoning history at inference time. Under this paradigm, the model does not become more capable in the sense of weight changes, but becomes progressively more effective on repeated task types — a mechanism we term inference-time memory accumulation.
This stands in contrast to existing paradigms: fine-tuning modifies parameters; RAG retrieves external documents; WLBS accumulates structured operational history native to the model's own reasoning process. We hypothesize that this enables a form of compounding performance: the more a model operates on a domain, the richer its world-line becomes, and the more precisely the resolution decay mechanism surfaces relevant historical reasoning for current decisions. The system becomes, in effect, increasingly adapted to its operational domain without any retraining.
This hypothesis requires substantial experimental validation and is presented as a direction for future research, not an established result. Key open questions include: how world-line entries interact with the model's parameter-based knowledge; how resolution decay should be calibrated for long-horizon LLM tasks; and whether inference-time memory accumulation can match the effectiveness of fine-tuning on domain-specific benchmarks. We present this direction because the OpenCraft preliminary results — specifically the stable focal routing to roles.py across 10 turns without fallback — suggest that structured operational history can materially influence task behavior. Whether this effect scales to general LLM training remains an open and important question.
### 6.5  Autonomous Agent Systems
For long-running autonomous agents, WLBS provides persistent spatial memory that accumulates operational experience. An agent builds a behavior graph of locations and transition dependencies; curvature accumulates at historically problematic locations; resolution decay focuses detailed memory on the current vicinity while maintaining summary awareness of the broader environment.
## 7.  Theoretical Connections
### 7.1  Minkowski Spacetime and the World-Line
The world-line concept is metaphorically inspired by Minkowski's formalization of special relativity [Minkowski, 1908], where a particle's complete history is a curve in four-dimensional spacetime. We emphasize that WLBS does not claim physical equivalence with relativistic world-lines. At the implementation level, a world-line is an append-only event log — a data structure familiar from distributed systems (write-ahead logs in databases, event sourcing in distributed architectures [Kleppmann, 2017]). The CS analogy is precise: just as a database write-ahead log preserves every committed transaction and supports replay from any historical state, a WLBS world-line preserves every execution event and supports context assembly from any historical snapshot. The inspiration from Minkowski is the intuition that history need not be retrieved — it is structurally present.
### 7.2  Backpropagation and Spatial Gradients
The curvature propagation algorithm is metaphorically inspired by gradient backpropagation [Rumelhart et al., 1986], but we emphasize that the two are not mathematically equivalent. Gradient backpropagation is grounded in the chain rule of calculus and serves an optimization objective. Curvature propagation, by contrast, is a heuristic spatial credit-assignment rule: failure signals decay exponentially with call-chain distance, and nodes closer to the root cause accumulate larger curvature increments. In CS terms, this is analogous to weighted fault propagation in reliability engineering, or to the blame-propagation step in spectrum-based fault localization [Jones et al., 2002] — both assign suspicion scores to components based on their causal proximity to observed failures. The key distinction is that WLBS propagates along the static call graph rather than test coverage matrices, enabling cross-file attribution without test execution. We use the term curvature propagation throughout to avoid conflation with neural network backpropagation.
### 7.3  The Fovea and Resolution Decay
The biological retina achieves high-resolution central vision and low-resolution peripheral vision through differential photoreceptor density. The fovea centralis has maximum cone density, decreasing toward the periphery. WLBS's resolution decay mechanism implements this architecture in the information domain: maximum resolution for behaviorally proximate history, decreasing resolution with distance. In CS terms, this is equivalent to a distance-weighted cache eviction policy: nearby nodes (cache hits) receive full detail, distant nodes (cache misses) receive only summary metadata. The behavioral distance metric plays the role of cache distance, and the three-tier resolution structure corresponds to L1/L2/L3 cache hierarchy — each tier trading resolution for coverage. Unlike LRU caches that evict by recency, WLBS evicts by structural distance, preserving task-relevant history regardless of when it occurred.
## 8.  Discussion
### 8.1  Why Information Should Not Be Translated
A curvature value of κ(n) = 0.80 (illustrative) on a node carries more information about that node's role in past failures than any natural language summary of those failures — and it carries it in a form that requires no parsing, no semantic interpretation, and no disambiguation. The gate reads a number and a graph position. It does not read a sentence about a number and a graph position. The difference matters when the reasoning chain is long and the context window is finite.
### 8.2  Growth Ceiling
We argue that the growth ceiling of WLBS is the complexity of the underlying domain, not an architectural constraint. The resolution decay mechanism ensures that context consumption grows sub-linearly with world-line length, since distant history is maximally compressed. The system's ability to improve is bounded only by the richness of the dependency structure it operates on.
### 8.3  Open Questions
The optimal values of α, λ, γ, and the resolution tier distance thresholds require systematic evaluation across domains. The dynamic dependency problem — call relationships that change at runtime — represents a fundamental limitation requiring runtime tracing coverage analysis. The extension of WLBS to LLM training requires formalizing dependency between training samples, which is an open research problem.
## 9.  Conclusion
We have presented the World-Line Behavior Space framework, which makes system history structurally present rather than externally stored, proposes spatial root-cause localization through curvature propagation, organizes historical information through resolution decay, and designs self-correcting reasoning loops without parameter updates.
Preliminary experiments demonstrate correct root-cause identification in a single cross-file dependency case and efficient behavior graph construction. Full benchmark evaluation is ongoing and required before generalizability claims can be made. The framework's domain-agnostic structure motivates future investigation across domains including microservice diagnosis, supply chain resilience, and clinical decision support.
The OpenCraft implementation will be released at: https://github.com/[to be announced]
Patent Notice
The technical methods described in this paper are the subject of the following pending patent applications filed in the People's Republic of China:

Acknowledgments
The author acknowledges the use of Claude (Anthropic) as a reasoning aid in formalizing the theoretical framework, including the world-line structure, the curvature propagation mechanism, and the resolution decay principle.
The author is deeply inspired by the foundational works of Yann LeCun, Yoshua Bengio, and Geoffrey Hinton on convolutional neural networks and the fovea analogy; David Rumelhart, Geoffrey Hinton, and Ronald Williams on backpropagation; Hermann Minkowski on spacetime geometry and the world-line formalism; Richard Feynman on path integrals; and Albert Einstein on special relativity.
The author thanks the open-source software engineering community for benchmark infrastructure.
## References
Allamanis, M., Barr, E. T., Devanbu, P., and Sutton, C. (2018). A survey of machine learning for big code and naturalness. ACM Computing Surveys, 51(4):81.
Chen, M., Tworek, J., Jun, H., Yuan, Q., et al. (2021). Evaluating large language models trained on code. arXiv preprint arXiv:2107.03374.
Einstein, A. (1905). Zur Elektrodynamik bewegter Körper. Annalen der Physik, 17(10):891–921.
Feynman, R. P. and Hibbs, A. R. (1965). Quantum Mechanics and Path Integrals. McGraw-Hill.
Jia, Y. and Harman, M. (2011). An analysis and survey of the development of mutation testing. IEEE Transactions on Software Engineering, 37(5):649–678.
Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., and Narasimhan, K. (2023). SWE-bench: Can language models resolve real-world GitHub issues? arXiv preprint arXiv:2310.06770. Published at ICLR 2024.
Jones, J. A., Harrold, M. J., and Stasko, J. (2002). Visualization of test information to assist fault localization. In Proceedings of ICSE 2002, pages 467–477.
Kirkpatrick, J., Pascanu, R., Rabinowitz, N., Veness, J., Desjardins, G., Rusu, A. A., Milan, K., Quan, J., Ramalho, T., Grabska-Barwinska, A., Hassabis, D., Clopath, C., Kumaran, D., and Hadsell, R. (2017). Overcoming catastrophic forgetting in neural networks. PNAS, 114(13):3521–3526.
LeCun, Y., Bottou, L., Bengio, Y., and Haffner, P. (1998). Gradient-based learning applied to document recognition. Proceedings of the IEEE, 86(11):2278–2324.
Lewis, P., Perez, E., Piktus, A., Petroni, F., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. NeurIPS 2020.
Minkowski, H. (1908). Die Grundgleichungen für die elektromagnetischen Vorgänge in bewegten Körpern. Nachrichten der Gesellschaft der Wissenschaften zu Göttingen, pages 53–111.
Parisi, G. I., Kemker, R., Part, J. L., Kanan, C., and Wermter, S. (2019). Continual lifelong learning with neural networks: A review. Neural Networks, 113:54–71.
Rumelhart, D. E., Hinton, G. E., and Williams, R. J. (1986). Learning representations by back-propagating errors. Nature, 323:533–536.
Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., and Yao, S. (2023). Reflexion: Language agents with verbal reinforcement learning. NeurIPS 2023. arXiv:2303.11366.
Tulving, E. (1983). Elements of Episodic Memory. Oxford University Press.
Wei, J., Wang, X., Schuurmans, D., Bosma, M., et al. (2022). Chain-of-thought prompting elicits reasoning in large language models. NeurIPS 2022.
Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, L., and Polosukhin, I. (2017). Attention is all you need. NeurIPS 2017. arXiv:1706.03762.
Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., et al. (2020). Language models are few-shot learners. NeurIPS 2020. arXiv:2005.14165.
Wang, L., Zhang, X., Su, H., and Zhu, J. (2023). A comprehensive survey of continual learning: Theory, method and application. arXiv:2302.00487.
Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., and Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. ICLR 2023. arXiv:2210.03629.
Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., and Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. UIST 2023. arXiv:2304.03442.
Mnih, V., Kavukcuoglu, K., Silver, D., Rusu, A. A., Veness, J., Bellemare, M. G., et al. (2015). Human-level control through deep reinforcement learning. Nature, 518:529–533.
Devlin, J., Chang, M.-W., Lee, K., and Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. NAACL 2019. arXiv:1810.04805.
De Lange, M., Aljundi, R., Masana, M., Parisot, S., Jia, X., Leonardis, A., Slabaugh, G., and Tuytelaars, T. (2022). A continual learning survey: Defying forgetting in classification tasks. IEEE TPAMI, 44:3366–3385.
Yao, S., Yu, D., Zhao, J., Shafran, I., Griffiths, T. L., Cao, Y., and Narasimhan, K. (2023). Tree of thoughts: Deliberate problem solving with large language models. NeurIPS 2023. arXiv:2305.10601.
Li, Z. and Hoiem, D. (2018). Learning without forgetting. IEEE TPAMI, 40(12):2935–2947.
Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C., Mishkin, P., et al. (2022). Training language models to follow instructions with human feedback. NeurIPS 2022. arXiv:2203.02155.
Liang, P., Bommasani, R., Lee, T., Tsipras, D., Soylu, D., Yasunaga, M., et al. (2022). Holistic evaluation of language models. arXiv:2211.09110.
Yang, J., Jimenez, C. E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K., and Press, O. (2024). SWE-agent: Agent-computer interfaces enable automated software engineering. In Advances in Neural Information Processing Systems (NeurIPS 2024). arXiv:2405.15793.