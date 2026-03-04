import { forwardRef, memo } from "react";
import RichBlock from "./RichBlock";
import StreamMessage from "./StreamMessage";
import CopyButton from "./CopyButton";

const UserMessage = memo(function UserMessage({ msg }) {
  return (
    <div className="msg user">
      {msg.content}
    </div>
  );
});

const AssistantMessage = memo(function AssistantMessage({ msg }) {
  return (
    <div className="msg assistant">
      {msg.content && <CopyButton text={msg.content} />}
      <RichBlock className="assistant-body" text={msg.content} />
    </div>
  );
});

function SkeletonMessages() {
  return (
    <>
      <div className="skeleton skeleton-msg" />
      <div className="skeleton skeleton-msg" />
      <div className="skeleton skeleton-msg" />
    </>
  );
}

const MessageList = forwardRef(function MessageList({ messages, isPending, currentRequestId, onScroll, loading }, ref) {
  return (
    <div id="messages" className="messages" ref={ref} data-testid="messages-list" onScroll={onScroll}>
      {loading && messages.length === 0 && <SkeletonMessages />}
      {messages.map((msg) => {
        if (msg.role === "assistant_stream") {
          const hasRequestContext = Boolean(currentRequestId) && Boolean(msg.requestId);
          const sameRequest = hasRequestContext ? msg.requestId === currentRequestId : true;
          const showTyping = Boolean(isPending && msg.status === "streaming" && sameRequest);
          return <StreamMessage key={msg.id} msg={msg} showTyping={showTyping} />;
        }
        return msg.role === "assistant" ? (
          <AssistantMessage key={msg.id} msg={msg} />
        ) : (
          <UserMessage key={msg.id} msg={msg} />
        );
      })}
    </div>
  );
});

export default memo(MessageList);
