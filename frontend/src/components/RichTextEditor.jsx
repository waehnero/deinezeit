import { useEditor, useEditorState, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { TextAlign } from '@tiptap/extension-text-align'
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
      // TipTap 3: Underline (und Link) sind im StarterKit enthalten; Link wird
      // hier nicht gebraucht und bleibt abgeschaltet.
      StarterKit.configure({ link: false }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
    ],
    content: value || '',
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML())
    },
  })

  // TipTap 3 rendert die Komponente nicht mehr bei jeder Änderung neu. Damit die
  // Toolbar den aktiven Zustand (fett, Liste, Ausrichtung …) weiter anzeigt,
  // wird er hier gezielt aus dem Editor gelesen.
  const zustand = useEditorState({
    editor,
    selector: ({ editor }) => editor ? {
      bold: editor.isActive('bold'),
      italic: editor.isActive('italic'),
      underline: editor.isActive('underline'),
      links: editor.isActive({ textAlign: 'left' }),
      zentriert: editor.isActive({ textAlign: 'center' }),
      rechts: editor.isActive({ textAlign: 'right' }),
      bulletList: editor.isActive('bulletList'),
      orderedList: editor.isActive('orderedList'),
    } : null,
  })

  // Sync external value changes (e.g. when switching tabs)
  useEffect(() => {
    if (!editor) return
    if (editor.getHTML() !== value) {
      editor.commands.setContent(value || '', { emitUpdate: false })
    }
  }, [value]) // eslint-disable-line

  if (!editor || !zustand) return null

  return (
    <div className="border border-neutral-200 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-primary-300">
      {/* Toolbar */}
      <div className="flex flex-wrap gap-0.5 px-2 py-1.5 border-b border-neutral-100 bg-neutral-50">
        <ToolbarBtn active={zustand.bold} onClick={() => editor.chain().focus().toggleBold().run()} title="Fett">
          <Bold size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={zustand.italic} onClick={() => editor.chain().focus().toggleItalic().run()} title="Kursiv">
          <Italic size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={zustand.underline} onClick={() => editor.chain().focus().toggleUnderline().run()} title="Unterstrichen">
          <UnderlineIcon size={14} />
        </ToolbarBtn>
        <div className="w-px bg-neutral-200 mx-1" />
        <ToolbarBtn active={zustand.links} onClick={() => editor.chain().focus().setTextAlign('left').run()} title="Links">
          <AlignLeft size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={zustand.zentriert} onClick={() => editor.chain().focus().setTextAlign('center').run()} title="Zentriert">
          <AlignCenter size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={zustand.rechts} onClick={() => editor.chain().focus().setTextAlign('right').run()} title="Rechts">
          <AlignRight size={14} />
        </ToolbarBtn>
        <div className="w-px bg-neutral-200 mx-1" />
        <ToolbarBtn active={zustand.bulletList} onClick={() => editor.chain().focus().toggleBulletList().run()} title="Liste">
          <List size={14} />
        </ToolbarBtn>
        <ToolbarBtn active={zustand.orderedList} onClick={() => editor.chain().focus().toggleOrderedList().run()} title="Nummerierte Liste">
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
