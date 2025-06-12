import path from 'path';

export function isPdfFile(filename = '', mime = '') {
  const ext = path.extname(filename).toLowerCase();
  return ext === '.pdf' || mime.toLowerCase() === 'application/pdf';
}
