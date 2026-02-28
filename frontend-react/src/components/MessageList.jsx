import { forwardRef } from "react";
import RichBlock from "./RichBlock";
import StreamMessage from "./StreamMessage";

const MessageList = forwardRef(function MessageList({ messages, isPending }, ref) {
  return (
    <div id="messages" className="messages" ref={ref} data-testid="messages-list">
      {messages.map((msg) => {
        if (msg.role === "assistant_stream") {
          return <StreamMessage key={msg.id} msg={msg} isPending={isPending} />;
        }
        return msg.role === "assistant" ? (
          <div key={msg.id} className="msg assistant">
            <RichBlock className="assistant-body" text={msg.content} />
          </div>
        ) : (
          <div key={msg.id} className="msg user">
            {msg.content}
          </div>
        );
      })}
    </div>
  );
});

export default MessageList;
