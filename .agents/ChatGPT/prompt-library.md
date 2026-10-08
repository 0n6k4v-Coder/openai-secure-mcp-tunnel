# Prompt Library

```text
📜 Codebase Ground Truth

### 1. Absolute Codebase Authority
The codebase in its current state is the single source of truth (Ground Truth). All answers,technical decisions, and architecture explanations must originate directly from the actual code.

### 2. Verify Before Speaking (Silent Verification)
If you are uncertain about any behavior, mechanism, or detail, do not guess or speculate. Silently inspect the codebase first before formulating your response.

### 3. Action Over Ignorance
Never tell the user "I don't know" or give up prematurely. Instead, actively inspect the files, search the code, trace the call paths, and provide a concrete answer based on your findings.

### 4. Radical Honesty on Non-Existent Features
If the codebase genuinely lacks the implementation, logic, or component asked about, state honestly and unequivocally that it does not exist in the codebase. Do not invent or assume phantom implementations.

### 5. Code Over Documentation
Do not blindly trust documentation, comments, or external references—they may be outdated or obsolete. Always verify against the active executable code and full repository implementation.
```

---

````text

1. **Deep research**

   * Research the latest official **MCP Server documentation**.
   * Research the latest official documentation for all relevant **technology-stack components**.
   * Research relevant and current **industry standards**.
   * Use the research to establish the technical basis for the implementation.

2. **Research findings summary**

   * Present the findings as a **clear table**, not just prose.
   * Include a unique **Finding ID** for every finding so it can be referenced later.
   * Design the table with the necessary columns to make each finding easy to understand and trace. For example:

   | Finding ID | Area | Finding | Why It Matters | Source / Standard | Version / Date | Implementation Impact |
   | ---------- | ---- | ------- | -------------- | ----------------- | -------------- | --------------------- |

   * Add other columns where useful, but keep the structure clear and practical.

3. **Implementation Deliverables**

1. **Identify all affected files**
   - Trace the implementation end-to-end using the repository as the source of truth.
   - Identify every file that must be **created, modified, or deleted**.
   - For each file, provide:
     - exact repository-relative path
     - action: `CREATE`, `MODIFY`, or `DELETE`
     - related Finding ID(s)
     - reason for the change
   - Map every Finding ID to the files and tests that address it.

2. **Deliver complete file contents in the conversation**
   - **Do not modify, create, delete, or overwrite any repository files.**
   - The implementation must be presented **entirely in the conversation**.
   - For every `CREATE` or `MODIFY` file, provide:
     - exact repository-relative path
     - action
     - related Finding ID(s)
     - **complete final file contents**
   - Do not provide snippets, partial files, diffs-only, placeholders, pseudocode, `...`, or omitted sections.
   - If a file is long, split its **complete contents** into clearly numbered consecutive parts while preserving the exact final file.
   - For `DELETE`, provide the exact path and explain why it should be removed.
   - The content shown must be the intended final repository state.

3. **Verify cross-file consistency**
   - Trace imports, function calls, types, configuration, registration, dependencies, security controls, tests, documentation, and runbooks across all affected files.
   - Verify that every referenced API actually exists in the repository or in a verified dependency.
   - **Do not invent APIs or assume unverified repository behavior.**
   - Ensure the proposed files work together as one coherent implementation.

4. **Validate the implementation honestly**
   - Provide the exact commands that should be used to validate the changes.
   - If commands can be executed safely without modifying repository files, run them where appropriate.
   - Classify every validation result as exactly one of:
     - `PASS` — executed and passed
     - `FAIL` — executed and failed
     - `NOT RUN` — applicable but not executed
     - `BLOCKED` — could not be executed because of a specific limitation
   - **Never claim that a test, check, build, or validation passed unless it was actually executed and passed.**

5. **Mandatory Completion Gate**
   - Do not mark Task 3 as complete until all of the following are satisfied:
     - complete file inventory is provided
     - every affected file has its full final contents
     - Finding IDs are traceable to implementation changes and tests
     - cross-file dependencies have been reviewed
     - security and compatibility have been reviewed
     - validation results are reported honestly
     - known limitations and unverified areas are explicitly disclosed
   - If something remains incomplete, clearly identify it and continue all feasible work before stopping.

6. **No false completion**
   - Analysis, architecture, recommendations, file inventories, diffs, or recovery procedures **do not constitute implementation delivery**.
   - Do not claim repository changes were applied.
   - The repository must remain unchanged by this task.
   - The **conversation itself is the implementation deliverable**.


4. **Complete Step-By-Step Runbook**

* Generate the complete runbook **directly in this conversation**.
* **Do not create or generate a file.**
* **Do not use a text editor or document editor.**
* The runbook must be **simple, clear, direct, explicit, concise, and complete**.
* Include **only the steps required** to implement, configure, run, test, verify, and complete the solution.
* Do not include unrelated information, optional steps, or unnecessary explanations.
* Assume the user will execute the commands **exactly as written**.
* Do not require the user to determine missing implementation details independently.

Present the runbook in a **strict sequential order**:

```text
Step 1
Step 2
Step 3
...
```

For every step, include exactly:

**Action**
What the user must do.

**Command**
The exact command(s) the user must run, when applicable.

**File**
Only the **file path/name** when a file must be created or modified.
Do **not** repeat the file contents here; the complete contents are already provided in Section 3.

**Expected Result**
The exact result the user should see or the condition that must be true before continuing.

**Related Finding IDs**
`F-001, F-004, F-009`

Rules:

* Every implementation, configuration, security, testing, and verification step must include **Related Finding IDs**.
* The Finding IDs must correspond directly to the research findings supporting that step.
* Use **existing research Finding IDs only**.
* **Do not invent new Finding IDs.**
* Every command must be explicit and copy-pasteable.
* Every expected result must be concrete and verifiable.
* When a step requires creating or modifying a file, identify the file by its **exact path**, but do not repeat its contents.
* The runbook must cover the complete process **from start to finish**, including:

  * prerequisites
  * environment/configuration
  * file creation/modification
  * dependency installation/update
  * build
  * service startup
  * verification
  * functional testing
  * security verification
  * failure checks required before declaring success
* The final step must define the **final acceptance criteria** for the implementation.
* The complete runbook must be executable **without the user having to infer, invent, or fill in missing steps**.
* Section 3 contains the complete file contents. Section 4 contains the **execution procedure only**.
````

---

```text
Let's apply these solutions directly to the codebase in the sandbox using Project Jupyter.
```

```text
Create unit tests and integration tests for the features you've implemented.
```

```text
Updated item in e2e test documents as well.
```