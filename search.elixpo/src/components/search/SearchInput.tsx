'use client';

import { useRef, useCallback, KeyboardEvent } from 'react';
import { ArrowUp, Globe, Cpu, Paperclip, Mic } from 'lucide-react';

interface SearchInputProps {
  onSend: (query: string) => void;
  disabled?: boolean;
}

export default function SearchInput({ onSend, disabled }: SearchInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const value = textareaRef.current?.value.trim();
    if (!value || disabled) return;
    onSend(value);
    if (textareaRef.current) {
      textareaRef.current.value = '';
      textareaRef.current.style.height = 'auto';
    }
  }, [onSend, disabled]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 300) + 'px';
  };

  return (
    <div className="relative bg-transparent p-[5px] w-full flex">
      <div className="max-w-[768px] w-full mx-auto flex flex-col gap-2 bg-[#2a2b2d] rounded-3xl px-4 py-3 border border-[#333] shadow-[0px_-10px_20px_#111] focus-within:border-[#444ce7] transition-colors">
        <textarea
          ref={textareaRef}
          placeholder="Ask anything..."
          className="flex-grow bg-transparent resize-none text-white text-lg placeholder-gray-500 focus:outline-none px-1 min-h-[28px] max-h-[300px]"
          rows={1}
          autoComplete="off"
          spellCheck={false}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />

        <div className="flex items-center justify-between text-gray-400">
          <div className="flex items-center gap-1 bg-[#191b1b] rounded-lg p-0.5">
            <button className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[#32aab5] border border-[#32aab5] bg-[#0a2528] text-xs font-medium">
              <Globe size={14} />
              <span>Web</span>
            </button>
            <button className="p-1.5 hover:text-white transition-colors rounded-lg hover:bg-[#333]">
              <Cpu size={16} />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button className="p-1.5 hover:text-white transition-colors">
              <Paperclip size={18} />
            </button>
            <button className="p-1.5 hover:text-white transition-colors">
              <Mic size={18} />
            </button>
            <button
              onClick={handleSend}
              disabled={disabled}
              className="bg-[#444ce7] hover:bg-[#5558e8] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl p-2 transition-colors"
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
