export async function writeTextToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fallback to execCommand below for browsers or webviews with restricted clipboard access.
    }
  }

  if (typeof document === "undefined" || !document.body) {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  textarea.style.top = "0";
  textarea.style.left = "-9999px";

  const selection = document.getSelection();
  const originalRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
  const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  try {
    return typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(textarea);
    if (originalRange && selection) {
      selection.removeAllRanges();
      selection.addRange(originalRange);
    }
    activeElement?.focus();
  }
}
