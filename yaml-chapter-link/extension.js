const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  console.log('yaml-chapter-link activated!');

  // Approach 1: DocumentLinkProvider - creates clickable underlined links
  const linkProvider = vscode.languages.registerDocumentLinkProvider(
    { language: 'yaml', scheme: 'file' },
    new ChapterDocumentLinkProvider()
  );

  // Approach 2: DefinitionProvider - Ctrl+Click / F12
  const defProvider = vscode.languages.registerDefinitionProvider(
    { language: 'yaml', scheme: 'file' },
    new ChapterDefinitionProvider()
  );

  context.subscriptions.push(linkProvider, defProvider);
}

class ChapterDocumentLinkProvider {
  /**
   * @param {vscode.TextDocument} document
   * @param {vscode.CancellationToken} token
   */
  provideDocumentLinks(document, token) {
    const links = [];
    const pattern = /v\d+_c\d+_s\d+/g;

    for (let i = 0; i < document.lineCount; i++) {
      if (token.isCancellationRequested) break;

      const line = document.lineAt(i).text;
      let match;

      while ((match = pattern.exec(line)) !== null) {
        const chapterKey = match[0];
        const targetPath = this._findFile(document, chapterKey);

        if (targetPath) {
          const startPos = new vscode.Position(i, match.index);
          const endPos = new vscode.Position(i, match.index + chapterKey.length);
          const range = new vscode.Range(startPos, endPos);
          const link = new vscode.DocumentLink(range, vscode.Uri.file(targetPath));
          link.tooltip = `Open ${chapterKey}.md`;
          links.push(link);
        }
      }
    }

    return links;
  }

  /**
   * @param {vscode.TextDocument} document
   * @param {string} chapterKey
   */
  _findFile(document, chapterKey) {
    const mdFilename = chapterKey + '.md';
    const yamlDir = path.dirname(document.uri.fsPath);

    // Try: same directory / translated
    const paths = [
      path.join(yamlDir, 'translated', mdFilename),
      path.join(path.dirname(yamlDir), 'translated', mdFilename),
      path.join(yamlDir, '..', 'truyen', 'translated', mdFilename),
    ];

    for (const p of paths) {
      if (fs.existsSync(p)) {
        return p;
      }
    }
    return null;
  }
}

class ChapterDefinitionProvider {
  provideDefinition(document, position, token) {
    const line = document.lineAt(position.line).text;
    const pattern = /v\d+_c\d+_s\d+/g;
    let match;

    while ((match = pattern.exec(line)) !== null) {
      const start = match.index;
      const end = start + match[0].length;

      if (position.character >= start && position.character <= end) {
        const chapterKey = match[0];
        const mdFilename = chapterKey + '.md';
        const yamlDir = path.dirname(document.uri.fsPath);

        const paths = [
          path.join(yamlDir, 'translated', mdFilename),
          path.join(path.dirname(yamlDir), 'translated', mdFilename),
        ];

        for (const p of paths) {
          if (fs.existsSync(p)) {
            return new vscode.Location(
              vscode.Uri.file(p),
              new vscode.Position(0, 0)
            );
          }
        }
        return null;
      }
    }
    return null;
  }
}

function deactivate() {}

module.exports = {
  activate,
  deactivate
};
