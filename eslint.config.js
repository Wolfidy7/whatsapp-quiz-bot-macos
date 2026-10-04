import sonarjs from 'eslint-plugin-sonarjs';
export default [{files: ['quiz_app/static/*.js'], plugins: {sonarjs},
  rules: {'sonarjs/cognitive-complexity': ['error', 10]}}];
