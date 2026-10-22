# Optional selected-story CPU trial dependencies

The [candidate](../docs/SELECTED_SOURCE_STORY_CPU_CANDIDATE.md) and its
[optional lock](../config/requirements-selected-story-cpu-trial.lock) are separate
from the normal API/development dependencies. No model or binary is distributed
in this source tree, and no optional runtime has been installed or qualified.

| Candidate | Declared upstream license | Upstream source |
| --- | --- | --- |
| llama-cpp-python 0.3.36 | MIT | [pinned project metadata](https://github.com/abetlen/llama-cpp-python/blob/1652066e0af45f2313b339670ef9555e8a54e545/pyproject.toml) |
| NumPy 2.3.4 | BSD-3-Clause | [release metadata](https://github.com/numpy/numpy/blob/v2.3.4/LICENSE.txt) |
| diskcache 5.6.3 | Apache-2.0 | [release metadata](https://pypi.org/pypi/diskcache/5.6.3/json) |
| Jinja2 3.1.6 | BSD-3-Clause | [release metadata](https://github.com/pallets/jinja/blob/3.1.6/LICENSE.txt) |
| Qwen2.5-1.5B-Instruct-GGUF Q4_K_M | Apache-2.0 | [pinned model license](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/91cad51170dc346986eccefdc2dd33a9da36ead9/LICENSE) |

The remaining API contract dependencies reuse the existing API lock and notices.
Retain all wheel license/notice files and bundled native dependency notices when
acquiring/installing the candidate. Record the model license outside its single
GGUF directory. The compiled wheel's contents and bundled-library notices still
need inspection; a package's declared license does not describe every component
of its binary distribution. This source pin is not a production provider choice.
