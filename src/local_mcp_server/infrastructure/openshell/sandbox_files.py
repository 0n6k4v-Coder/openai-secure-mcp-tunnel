from __future__ import annotations

import json
import os
import shlex

from ...workspace.formatting import _FORMATTER_HELPER

SANDBOX_WORKSPACE_ROOT = "/workspace/project"
MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000
MAX_RELATIVE_PATH_BYTES = 4_096

_NODE_FILE_HELPER = r"""
const fs = require('fs');
const path = require('path');
const root = path.resolve('/workspace/project');

function checkRelative(rel) {
    if (!rel) { console.error('Path must not be empty.'); process.exit(1); }
    if (path.isAbsolute(rel)) { console.error('Requested path must be relative.'); process.exit(1); }
    const resolved = path.resolve(root, rel);
    if (!resolved.startsWith(root + path.sep) && resolved !== root) {
        console.error('Requested path is outside the workspace.'); process.exit(1);
    }
    return resolved;
}

const op = process.argv[1];
const arg1 = process.argv[2];
const arg2 = process.argv[3];
const arg3 = process.argv[4];
const arg4 = process.argv[5];

if (op === 'list') {
    let results = [];
    function walk(dir) {
        try {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    walk(full);
                } else if (entry.isFile()) {
                    const resolved = fs.realpathSync(full);
                    if (resolved.startsWith(root + path.sep) || resolved === root) {
                        results.push(path.relative(root, resolved));
                    }
                }
            }
        } catch (_) {}
    }
    walk(root);
    console.log(JSON.stringify(Array.from(new Set(results)).sort()));
} else if (op === 'view') {
    const resolved = checkRelative(arg1);
    let stat;
    try { stat = fs.statSync(resolved); } catch (_) { console.error('Requested path is not a regular file.'); process.exit(1); }
    if (!stat.isFile()) { console.error('Requested path is not a regular file.'); process.exit(1); }
    const totalBytes = stat.size;
    let offset = 0;
    if (arg4 && !isNaN(parseInt(arg4, 10))) {
        offset = Math.max(0, parseInt(arg4, 10));
    }
    const fd = fs.openSync(resolved, 'r');
    const maxReadBytes = Math.min(2000000, Math.max(0, totalBytes - offset));
    const buf = Buffer.alloc(maxReadBytes);
    const bytesRead = fs.readSync(fd, buf, 0, maxReadBytes, offset);
    fs.closeSync(fd);

    const relPath = path.relative(root, resolved);
    const isBinary = buf.slice(0, Math.min(8000, bytesRead)).includes(0);
    if (isBinary) {
        process.stdout.write(`File Path: \`file:///workspace/project/${relPath}\`\nTotal Bytes: ${totalBytes}\n[Binary file]\n`);
        process.exit(0);
    }

    const text = buf.subarray(0, bytesRead).toString('utf8');
    const allLines = text.split(/\r?\n/);
    const totalLines = allLines.length;

    let sLine = 1;
    let eLine = Math.min(totalLines, 800);
    const parsedStart = arg2 ? parseInt(arg2, 10) : NaN;
    const parsedEnd = arg3 ? parseInt(arg3, 10) : NaN;

    if (!isNaN(parsedStart) && !isNaN(parsedEnd)) {
        sLine = Math.max(1, parsedStart);
        eLine = Math.min(totalLines, Math.max(sLine, parsedEnd));
        if (eLine - sLine + 1 > 800) eLine = sLine + 799;
    } else if (!isNaN(parsedStart)) {
        sLine = Math.max(1, parsedStart);
        eLine = Math.min(totalLines, sLine + 799);
    } else if (!isNaN(parsedEnd)) {
        eLine = Math.min(totalLines, Math.max(1, parsedEnd));
        sLine = Math.max(1, eLine - 799);
    }

    const header = `File Path: \`file:///workspace/project/${relPath}\`\nTotal Lines: ${totalLines}\nTotal Bytes: ${totalBytes}\nShowing lines ${sLine} to ${eLine}\nThe following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.\n`;

    let out = header;
    let currentBytes = Buffer.byteLength(header, 'utf8');
    let truncatedByBytes = false;
    let actualEnd = sLine - 1;

    for (let i = sLine - 1; i < eLine; i++) {
        const lineNum = i + 1;
        const lineContent = allLines[i] !== undefined ? allLines[i] : '';
        const lineStr = `${lineNum}: ${lineContent}\n`;
        const lineByteLen = Buffer.byteLength(lineStr, 'utf8');
        if (currentBytes + lineByteLen > 46080 && (i > sLine - 1)) {
            truncatedByBytes = true;
            break;
        }
        out += lineStr;
        currentBytes += lineByteLen;
        actualEnd = lineNum;
    }

    if (actualEnd < totalLines || truncatedByBytes) {
        out += '\nThe above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.';
    }
    process.stdout.write(out);
} else if (op === 'read') {
    const resolved = checkRelative(arg1);
    let stat;
    try { stat = fs.statSync(resolved); } catch (_) { console.error('Requested path is not a regular file.'); process.exit(1); }
    if (!stat.isFile()) { console.error('Requested path is not a regular file.'); process.exit(1); }
    if (stat.size > 1000000) {
        const fd = fs.openSync(resolved, 'r');
        const buf = Buffer.alloc(200000);
        const bytesRead = fs.readSync(fd, buf, 0, 200000, 0);
        fs.closeSync(fd);
        process.stdout.write(buf.subarray(0, bytesRead).toString('utf8') + `\n\n[Content truncated: showing first ${bytesRead} bytes of ${stat.size} bytes]`);
        process.exit(0);
    }
    try {
        const content = fs.readFileSync(resolved, 'utf8');
        process.stdout.write(content);
    } catch (_) {
        console.error('Requested file is not valid UTF-8 text.'); process.exit(1);
    }
} else if (op === 'write') {
    const resolved = checkRelative(arg1);
    const overwrite = arg2 === 'true';
    try {
        if (fs.lstatSync(path.join(root, arg1)).isSymbolicLink()) {
            console.error('Requested path must not be a symbolic link.'); process.exit(1);
        }
    } catch (_) {}
    if (fs.existsSync(resolved)) {
        if (!fs.statSync(resolved).isFile()) {
            console.error('Requested path already exists and is not a regular file.'); process.exit(1);
        }
        if (!overwrite) {
            console.error('File already exists and overwrite is set to False.'); process.exit(1);
        }
    }
    const chunks = [];
    process.stdin.on('data', c => chunks.push(c));
    process.stdin.on('end', () => {
        const buf = Buffer.concat(chunks);
        if (buf.length > 1000000) { console.error('Content is too large.'); process.exit(1); }
        fs.mkdirSync(path.dirname(resolved), { recursive: true });
        fs.writeFileSync(resolved, buf);
        process.stdout.write(JSON.stringify({ path: path.relative(root, resolved), formatting: 'skipped: node environment' }));
    });
} else if (op === 'replace') {
    const resolved = checkRelative(arg1);
    const allowMultiple = arg2 === 'true';
    try {
        if (fs.lstatSync(path.join(root, arg1)).isSymbolicLink()) {
            console.error('Requested path must not be a symbolic link.'); process.exit(1);
        }
    } catch (_) {}
    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        console.error('Target file does not exist or is not a regular file.'); process.exit(1);
    }
    const chunks = [];
    process.stdin.on('data', c => chunks.push(c));
    process.stdin.on('end', () => {
        const rawPayload = Buffer.concat(chunks).toString('utf8');
        const payload = JSON.parse(rawPayload);
        const targetContent = payload.target_content;
        const replacementContent = payload.replacement_content;
        if (!targetContent) { console.error('target_content must not be empty.'); process.exit(1); }
        let original;
        try { original = fs.readFileSync(resolved, 'utf8'); } catch (_) { console.error('Target file is not valid UTF-8 text.'); process.exit(1); }
        const count = original.split(targetContent).length - 1;
        if (count === 0) { console.error('target_content not found in file.'); process.exit(1); }
        if (count > 1 && !allowMultiple) {
            console.error(`target_content occurred ${count} times in file. Provide more context or set allow_multiple=True.`);
            process.exit(1);
        }
        const updated = allowMultiple ? original.replaceAll(targetContent, replacementContent) : original.replace(targetContent, replacementContent);
        const updatedBuf = Buffer.from(updated, 'utf8');
        if (updatedBuf.length > 1000000) { console.error('Updated content exceeds maximum allowed size.'); process.exit(1); }
        fs.writeFileSync(resolved, updatedBuf);
        process.stdout.write(JSON.stringify({ path: path.relative(root, resolved), formatting: 'skipped: node environment' }));
    });
} else if (op === 'mkdir') {
    const resolved = checkRelative(arg1);
    if (fs.existsSync(resolved)) {
        console.error('A file or directory already exists at that path.'); process.exit(1);
    }
    fs.mkdirSync(resolved, { recursive: false });
    process.stdout.write(path.relative(root, resolved));
} else if (op === 'rename') {
    const src = checkRelative(arg1);
    const dst = checkRelative(arg2);
    if (!fs.existsSync(src)) { console.error('Source path does not exist.'); process.exit(1); }
    if (fs.existsSync(dst)) { console.error('Destination path already exists.'); process.exit(1); }
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.renameSync(src, dst);
    process.stdout.write(path.relative(root, dst));
} else if (op === 'delete_file') {
    const resolved = checkRelative(arg1);
    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        console.error('Requested path is not a regular file.'); process.exit(1);
    }
    fs.unlinkSync(resolved);
    process.stdout.write(path.relative(root, resolved));
} else if (op === 'delete_dir') {
    if (arg1 === '.' || path.join(root, arg1) === root) {
        console.error('Deleting the workspace root is not allowed.'); process.exit(1);
    }
    const resolved = checkRelative(arg1);
    try {
        if (fs.lstatSync(path.join(root, arg1)).isSymbolicLink()) {
            console.error('Requested path must not be a symbolic link.'); process.exit(1);
        }
    } catch (_) {}
    if (!fs.existsSync(resolved)) { console.error('Requested directory does not exist.'); process.exit(1); }
    if (!fs.statSync(resolved).isDirectory()) { console.error('Requested path is not a directory.'); process.exit(1); }
    fs.rmSync(resolved, { recursive: true, force: true });
    process.stdout.write(path.relative(root, resolved));
}
""".strip()

_LIST_FILES_COMMAND = r"""python -c '
import json
import os
root = "/workspace/project"
results = []
for base, directories, files in os.walk(root, followlinks=False):
    for name in files:
        path = os.path.join(base, name)
        resolved = os.path.realpath(path)
        try:
            common = os.path.commonpath([root, resolved])
        except ValueError:
            continue
        if common == root and os.path.isfile(resolved):
            results.append(os.path.relpath(resolved, root))
print(json.dumps(sorted(set(results)), ensure_ascii=False))
'"""

_READ_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

resolved = os.path.realpath(os.path.join(root, relative_path))
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")

if os.path.getsize(resolved) > 1_000_000:
    with open(resolved, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read(200_000)
    sys.stdout.write(content + f"\n\n[Content truncated: showing first 200,000 characters of {os.path.getsize(resolved)} bytes]")
    raise SystemExit(0)

try:
    with open(resolved, "r", encoding="utf-8") as handle:
        content = handle.read()
except UnicodeDecodeError as exc:
    raise SystemExit("Requested file is not valid UTF-8 text.") from exc

sys.stdout.write(content)
""".strip()

_VIEW_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1] if len(sys.argv) > 1 else ""

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

resolved = os.path.realpath(os.path.join(root, relative_path))
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")

total_bytes = os.path.getsize(resolved)

content_offset = 0
if len(sys.argv) > 4 and sys.argv[4]:
    try:
        content_offset = max(0, int(sys.argv[4]))
    except ValueError:
        content_offset = 0

with open(resolved, "rb") as f:
    if content_offset > 0:
        f.seek(content_offset)
    max_read_bytes = min(2_000_000, max(0, total_bytes - content_offset))
    raw_bytes = f.read(max_read_bytes)

rel_path = os.path.relpath(resolved, root)
is_binary = b"\x00" in raw_bytes[:min(8000, len(raw_bytes))]
if is_binary:
    sys.stdout.write(f"File Path: `file:///workspace/project/{rel_path}`\nTotal Bytes: {total_bytes}\n[Binary file]\n")
    sys.exit(0)

try:
    text = raw_bytes.decode("utf-8")
except UnicodeDecodeError:
    text = raw_bytes.decode("utf-8", errors="replace")

all_lines = text.splitlines(keepends=False)
total_lines = len(all_lines)

parsed_start = None
if len(sys.argv) > 2 and sys.argv[2]:
    try:
        parsed_start = int(sys.argv[2])
    except ValueError:
        pass

parsed_end = None
if len(sys.argv) > 3 and sys.argv[3]:
    try:
        parsed_end = int(sys.argv[3])
    except ValueError:
        pass

s_line = 1
e_line = min(total_lines, 800)

if parsed_start is not None and parsed_end is not None:
    s_line = max(1, parsed_start)
    e_line = min(total_lines, max(s_line, parsed_end))
    if e_line - s_line + 1 > 800:
        e_line = s_line + 799
elif parsed_start is not None:
    s_line = max(1, parsed_start)
    e_line = min(total_lines, s_line + 799)
elif parsed_end is not None:
    e_line = min(total_lines, max(1, parsed_end))
    s_line = max(1, e_line - 799)

header = (
    f"File Path: `file:///workspace/project/{rel_path}`\n"
    f"Total Lines: {total_lines}\n"
    f"Total Bytes: {total_bytes}\n"
    f"Showing lines {s_line} to {e_line}\n"
    "The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.\n"
)

out = [header]
current_bytes = len(header.encode("utf-8"))
truncated_by_bytes = False
actual_end = s_line - 1

for i in range(s_line - 1, e_line):
    line_num = i + 1
    line_content = all_lines[i] if i < len(all_lines) else ""
    line_str = f"{line_num}: {line_content}\n"
    line_byte_len = len(line_str.encode("utf-8"))
    if current_bytes + line_byte_len > 46080 and i > (s_line - 1):
        truncated_by_bytes = True
        break
    out.append(line_str)
    current_bytes += line_byte_len
    actual_end = line_num

if actual_end < total_lines or truncated_by_bytes:
    out.append("\nThe above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.")

sys.stdout.write("".join(out))
""".strip()

_WRITE_TO_FILE_SCRIPT = _FORMATTER_HELPER + r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]
overwrite = sys.argv[2].lower() == "true"

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if os.path.exists(resolved):
    if not os.path.isfile(resolved):
        raise SystemExit("Requested path already exists and is not a regular file.")
    if not overwrite:
        raise SystemExit("File already exists and overwrite is set to False.")

content = sys.stdin.buffer.read()
if len(content) > 1_000_000:
    raise SystemExit("Content is too large.")

try:
    content_text = content.decode("utf-8")
except UnicodeDecodeError as exc:
    raise SystemExit("Content is not valid UTF-8 text.") from exc
content_text, format_status = _format_text(relative_path, content_text)
content = content_text.encode("utf-8")
if len(content) > 1_000_000:
    raise SystemExit("Formatted content exceeds maximum allowed size.")

parent = os.path.dirname(resolved)
os.makedirs(parent, exist_ok=True)

with open(resolved, "wb") as handle:
    handle.write(content)

sys.stdout.write(json.dumps({"path": os.path.relpath(resolved, root), "formatting": format_status}))
""".strip()

_REPLACE_FILE_CONTENT_SCRIPT = _FORMATTER_HELPER + r"""
import json
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]
allow_multiple = sys.argv[2].lower() == "true"

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Target file does not exist or is not a regular file.")

raw_payload = sys.stdin.buffer.read().decode("utf-8")
payload = json.loads(raw_payload)
target_content = payload["target_content"]
replacement_content = payload["replacement_content"]

if not target_content:
    raise SystemExit("target_content must not be empty.")

try:
    with open(resolved, "r", encoding="utf-8") as handle:
        original = handle.read()
except UnicodeDecodeError as exc:
    raise SystemExit("Target file is not valid UTF-8 text.") from exc

count = original.count(target_content)
if count == 0:
    raise SystemExit("target_content not found in file.")
if count > 1 and not allow_multiple:
    raise SystemExit(f"target_content occurred {count} times in file. Provide more context or set allow_multiple=True.")

updated = original.replace(target_content, replacement_content) if allow_multiple else original.replace(target_content, replacement_content, 1)
updated, format_status = _format_text(relative_path, updated)

if len(updated.encode("utf-8")) > 1_000_000:
    raise SystemExit("Updated content exceeds maximum allowed size.")

with open(resolved, "w", encoding="utf-8") as handle:
    handle.write(updated)

sys.stdout.write(json.dumps({"path": os.path.relpath(resolved, root), "formatting": format_status}))
""".strip()


_CREATE_DIRECTORY_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if os.path.exists(resolved):
    raise SystemExit("A file or directory already exists at that path.")

os.makedirs(resolved, exist_ok=False)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_RENAME_PATH_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]
new_relative_path = sys.argv[2]

if not relative_path or not new_relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path) or os.path.isabs(new_relative_path):
    raise SystemExit("Requested path must be relative.")

source = os.path.realpath(os.path.join(root, relative_path))
destination = os.path.realpath(os.path.join(root, new_relative_path))

for target in (source, destination):
    try:
        common = os.path.commonpath([root, target])
    except ValueError as exc:
        raise SystemExit("Requested path is outside the workspace.") from exc
    if common != root:
        raise SystemExit("Requested path is outside the workspace.")

if not os.path.exists(source):
    raise SystemExit("Source path does not exist.")

if os.path.exists(destination):
    raise SystemExit("Destination path already exists.")

dest_parent = os.path.dirname(destination)
os.makedirs(dest_parent, exist_ok=True)
os.rename(source, destination)
sys.stdout.write(os.path.relpath(destination, root))
""".strip()

_DELETE_FILE_SCRIPT = r"""
import os
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root:
    raise SystemExit("Requested path is outside the workspace.")

if not os.path.isfile(resolved):
    raise SystemExit("Requested path is not a regular file.")

os.unlink(resolved)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()

_DELETE_DIRECTORY_SCRIPT = r"""
import os
import shutil
import sys

root = os.path.realpath("/workspace/project")
relative_path = sys.argv[1]

if not relative_path:
    raise SystemExit("Path must not be empty.")
if os.path.isabs(relative_path):
    raise SystemExit("Requested path must be relative.")

requested = os.path.join(root, relative_path)
if requested == root or relative_path == ".":
    raise SystemExit("Deleting the workspace root is not allowed.")
if os.path.islink(requested):
    raise SystemExit("Requested path must not be a symbolic link.")

resolved = os.path.realpath(requested)
try:
    common = os.path.commonpath([root, resolved])
except ValueError as exc:
    raise SystemExit("Requested path is outside the workspace.") from exc

if common != root or resolved == root:
    raise SystemExit("Deleting the workspace root is not allowed." if resolved == root else "Requested path is outside the workspace.")

if not os.path.exists(resolved):
    raise SystemExit("Requested directory does not exist.")

if not os.path.isdir(resolved):
    raise SystemExit("Requested path is not a directory.")

shutil.rmtree(resolved)
sys.stdout.write(os.path.relpath(resolved, root))
""".strip()


def _validate_relative_path(relative_path: str) -> None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Path must not be empty.")
    if "\x00" in relative_path:
        raise ValueError("Path must not contain NUL bytes.")
    if len(relative_path.encode("utf-8")) > MAX_RELATIVE_PATH_BYTES:
        raise ValueError("Path is too long.")
    if relative_path.startswith("/") or os.path.isabs(relative_path):
        raise ValueError("Requested path must be relative.")


def _validate_content(content: str) -> bytes:
    if not isinstance(content, str):
        raise ValueError("Content must be a string.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        raise ValueError("Content is too large.")
    return encoded


def execute_sandbox(*args, **kwargs):
    from .sandbox import execute_sandbox as _execute_sandbox

    return _execute_sandbox(*args, **kwargs)


def validate_name(*args, **kwargs):
    from ...sandbox.policy import validate_name as _validate_name

    return _validate_name(*args, **kwargs)


def _execute_workspace_command(
    sandbox_name: str,
    command: str,
    *,
    stdin: bytes | str | None = None,
) -> str:
    validate_name(sandbox_name)
    kwargs = {}
    if stdin is not None:
        kwargs["stdin"] = stdin
    result = json.loads(
        execute_sandbox(
            name=sandbox_name,
            command=command,
            **kwargs,
        )
    )
    if result.get("return_code") != 0:
        stderr = result.get("stderr", "")
        message = stderr.strip() if isinstance(stderr, str) else ""
        raise ValueError(message or "Sandbox workspace command failed.")
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str):
        raise RuntimeError("Sandbox workspace command returned invalid stdout.")
    return stdout


def _formatting_result(output: str) -> str:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return output
    if not isinstance(payload, dict) or not isinstance(payload.get("path"), str):
        return output
    path = payload["path"]
    status = payload.get("formatting")
    if status is None:
        return path
    if not isinstance(status, str):
        raise RuntimeError("Sandbox write returned an invalid formatting status.")
    return f"{path}\nFormatting: {status}"


def _wrap_polyglot_command(py_code: str, node_op: str, args: list[str]) -> str:
    escaped_args = " ".join(shlex.quote(a) for a in args)
    return (
        "sh -c "
        + shlex.quote(
            f"""
if command -v python3 >/dev/null 2>&1; then
    python3 -c {shlex.quote(py_code)} {escaped_args}
elif command -v python >/dev/null 2>&1; then
    python -c {shlex.quote(py_code)} {escaped_args}
elif command -v node >/dev/null 2>&1; then
    node -e {shlex.quote(_NODE_FILE_HELPER)} {shlex.quote(node_op)} {escaped_args}
else
    echo "No supported python or node interpreter found in sandbox." >&2
    exit 1
fi
"""
        )
    )


def list_sandbox_workspace_files(sandbox_name: str) -> list[str]:
    command = _wrap_polyglot_command(_LIST_FILES_COMMAND.replace("python -c '", "").rstrip("'\n"), "list", [])
    output = _execute_workspace_command(sandbox_name, command)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Sandbox workspace listing returned invalid JSON.") from exc
    if not isinstance(result, list) or not all(
        isinstance(value, str) for value in result
    ):
        raise RuntimeError("Sandbox workspace listing returned an invalid result.")
    return list(result)


def read_sandbox_workspace_text_file(sandbox_name: str, relative_path: str) -> str:
    _validate_relative_path(relative_path)
    command = _wrap_polyglot_command(_READ_FILE_SCRIPT, "read", [relative_path])
    return _execute_workspace_command(sandbox_name, command)


def view_sandbox_workspace_file(
    sandbox_name: str,
    relative_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    content_offset: int | None = None,
) -> str:
    _validate_relative_path(relative_path)
    args = [
        relative_path,
        str(start_line) if start_line is not None else "",
        str(end_line) if end_line is not None else "",
        str(content_offset) if content_offset is not None else "",
    ]
    command = _wrap_polyglot_command(_VIEW_FILE_SCRIPT, "view", args)
    return _execute_workspace_command(sandbox_name, command)



def write_sandbox_file(
    sandbox_name: str,
    relative_path: str,
    content: str,
    overwrite: bool = True,
) -> str:
    _validate_relative_path(relative_path)
    encoded = _validate_content(content)
    command = _wrap_polyglot_command(_WRITE_TO_FILE_SCRIPT, "write", [relative_path, "true" if overwrite else "false"])
    return _formatting_result(
        _execute_workspace_command(sandbox_name, command, stdin=encoded)
    )


def replace_sandbox_file_content(
    sandbox_name: str,
    relative_path: str,
    target_content: str,
    replacement_content: str,
    allow_multiple: bool = False,
) -> str:
    _validate_relative_path(relative_path)
    if not isinstance(target_content, str):
        raise ValueError("target_content must be a string.")
    if not isinstance(replacement_content, str):
        raise ValueError("replacement_content must be a string.")
    if not target_content:
        raise ValueError("target_content must not be empty.")

    payload = json.dumps(
        {
            "target_content": target_content,
            "replacement_content": replacement_content,
        }
    ).encode("utf-8")

    command = _wrap_polyglot_command(
        _REPLACE_FILE_CONTENT_SCRIPT,
        "replace",
        [relative_path, "true" if allow_multiple else "false"],
    )
    return _formatting_result(
        _execute_workspace_command(sandbox_name, command, stdin=payload)
    )


def create_sandbox_workspace_directory(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = _wrap_polyglot_command(_CREATE_DIRECTORY_SCRIPT, "mkdir", [relative_path])
    return _execute_workspace_command(sandbox_name, command)


def rename_sandbox_workspace_path(
    sandbox_name: str,
    relative_path: str,
    new_relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    _validate_relative_path(new_relative_path)
    command = _wrap_polyglot_command(_RENAME_PATH_SCRIPT, "rename", [relative_path, new_relative_path])
    return _execute_workspace_command(sandbox_name, command)


def delete_sandbox_workspace_file(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = _wrap_polyglot_command(_DELETE_FILE_SCRIPT, "delete_file", [relative_path])
    return _execute_workspace_command(sandbox_name, command)


def delete_sandbox_workspace_directory(
    sandbox_name: str,
    relative_path: str,
) -> str:
    _validate_relative_path(relative_path)
    command = _wrap_polyglot_command(_DELETE_DIRECTORY_SCRIPT, "delete_dir", [relative_path])
    return _execute_workspace_command(sandbox_name, command)
