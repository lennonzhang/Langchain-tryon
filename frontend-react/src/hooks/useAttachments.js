import { useCallback, useEffect, useRef, useState } from "react";
import { MAX_ATTACHMENTS, readFileAsDataUrl, extractVideoFrame, nextAttachId } from "../utils/media";

export function useAttachments(supportsMedia) {
  const fileInputRef = useRef(null);
  const [attachments, setAttachments] = useState([]);

  useEffect(() => {
    if (!supportsMedia) setAttachments([]);
  }, [supportsMedia]);

  const handleFilesSelected = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || []);
      if (files.length === 0) return;

      const remaining = MAX_ATTACHMENTS - attachments.length;
      const batch = files.slice(0, Math.max(0, remaining));

      const newItems = [];
      for (const file of batch) {
        try {
          const dataUrl = await readFileAsDataUrl(file);
          const type = file.type.startsWith("video/") ? "video" : "image";
          let thumbUrl = "";
          if (type === "video") {
            thumbUrl = await extractVideoFrame(file);
          }
          newItems.push({ id: nextAttachId(), file, dataUrl, type, name: file.name, thumbUrl });
        } catch {
          // skip unreadable files
        }
      }

      if (newItems.length > 0) {
        setAttachments((prev) => [...prev, ...newItems]);
      }

      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [attachments.length],
  );

  function removeAttachment(id) {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function clearAttachments() {
    setAttachments([]);
  }

  return { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments };
}
