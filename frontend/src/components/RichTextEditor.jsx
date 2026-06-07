import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextAlign from '@tiptap/extension-text-align'
import TextStyle from '@tiptap/extension-text-style'
import { useEffect } from 'react'
import {
  Bold, Italic, Underline as UnderlineIcon,
  AlignLeft, AlignCenter, AlignRight,
  List, ListOrdered, Minus
} from 'lucide-react'

function ToolbarBtn({ active, onClick, title, children }) {
  return (
    <button
      type="button"
      onMouseDown={e => { e.preventDefault(); onClick() }}
      title={title}
      className={`p-1.5 rounded text-sm transition ${
        active
          ? 'bg-primary-100 text-primary-700'
          : 'text-neutral-600 hover:bg-neutral-100'
      }`}
    >
      {children}
    </button>
  )
}

export default function RichTextEditor({ value, onChange, minHeight = '180px' }) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      TextStyle,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
    ],
    content: value || '',
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML())
    },
  })

  // Sync external value changes (e.g. when switching tabs)
  useEffect(() => {
    if (!editor) return
    if (editor.getHTML() !== value) {
      editor.commands.setContent(value || '', false)
    }
  }, [value]) // eslint-disable-line

  if (!editor) return null

  return (
    <div className="border border-neutral-200 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-primary-300">
      {/* Toolbar */}
      <div className="flex flex-wrap gap-0.5 px-2 py-1.5 border-b border-neutral-100 bg-neutral-50">
        <ToolbarBtn active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()} title="Fett">
          <Bold size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()} title="Kursiv">
          <Italic size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={editor.isActive('underline')} onClick={() => editor.chain().focus().toggleUnderline().run()} title="Unterstrichen">
          <UnderlineIcon size={14} />
        </ToolbarBtn>
        <div className="w-px bg-neutral-200 mx-1" />
        <ToolbarBtn active={editor.isActive({ textAlign: 'left' })} onClick={() => editor.chain().focus().setTextAlign('left').run()} title="Links">
          <AlignLeft size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={editor.isActive({ textAlign: 'center' })} onClick={() => editor.chain().focus().setTextAlign('center').run()} title="Zentriert">
          <AlignCenter size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={editor.isActive({ textAlign: 'right' })} onClick={() => editor.chain().focus().setTextAlign('right').run()} title="Rechts">
          <AlignRight size={14} />
        </ToolbarBtn>
        <div className="w-px bg-neutral-200 mx-1" />
        <ToolbarBtn active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()} title="Liste">
          <List size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()} title="Nummerierte Liste">
          <ListOrdered size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={false} onClick={() => editor.chain().focus().setHorizontalRule().run()} title="Trennlinie">
          <Minus size={14} />
        </ToolbarBtn>
      </div>

      {/* Editor area */}
      <EditorContent
        editor={editor}
        className="prose prose-sm max-w-none px-3 py-2 outline-none"
        style={{ minHeight }}
      />
    </div>
  )
}
