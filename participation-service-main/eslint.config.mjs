import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// Prettier owns formatting; ESLint checks correctness and TypeScript practice.
export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**', '.engine-artifacts/**', 'prisma/generated/**'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  { languageOptions: { globals: { ...globals.node, ...globals.jest } } },
  prettier,
);
