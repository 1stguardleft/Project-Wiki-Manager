import { useState } from "react";

interface TreeNode {
  name: string;
  path: string;
  isFile: boolean;
  children: TreeNode[];
}

function buildTree(files: string[]): TreeNode[] {
  const children: TreeNode[] = [];

  for (const filePath of files) {
    const parts = filePath.split("/");
    let nodes = children;

    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      const path = parts.slice(0, i + 1).join("/");
      const isFile = i === parts.length - 1;

      let node = nodes.find((n) => n.name === name);
      if (!node) {
        node = { name, path, isFile, children: [] };
        nodes.push(node);
      }
      nodes = node.children;
    }
  }

  return children;
}

function TreeNodeItem({
  node,
  depth,
  selectedPath,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const indent = depth * 16;

  if (node.isFile) {
    const isSelected = node.path === selectedPath;
    return (
      <button
        type="button"
        className={`tree-file${isSelected ? " tree-file--active" : ""}`}
        style={{ paddingLeft: `${indent + 20}px` }}
        onClick={() => onSelect(node.path)}
        title={node.path}
      >
        <span className="tree-icon">📄</span>
        {node.name}
      </button>
    );
  }

  return (
    <div>
      <button
        type="button"
        className="tree-folder"
        style={{ paddingLeft: `${indent}px` }}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="tree-icon">{open ? "▾" : "▸"}</span>
        {node.name}
      </button>
      {open && (
        <div>
          {node.children
            .slice()
            .sort((a, b) => {
              // 폴더 먼저, 그 다음 파일 / 알파벳순
              if (a.isFile !== b.isFile) return a.isFile ? 1 : -1;
              return a.name.localeCompare(b.name);
            })
            .map((child) => (
              <TreeNodeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
        </div>
      )}
    </div>
  );
}

interface FileTreeProps {
  files: string[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

export function FileTree({ files, selectedPath, onSelect }: FileTreeProps) {
  const roots = buildTree(files);

  if (roots.length === 0) {
    return <p className="tree-empty">표시할 파일이 없습니다.</p>;
  }

  return (
    <nav className="file-tree">
      {roots.map((node) => (
        <TreeNodeItem
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
        />
      ))}
    </nav>
  );
}
