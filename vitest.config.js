import {defineConfig} from 'vitest/config';
export default defineConfig({test:{environment:'jsdom',include:['tests/frontend/*.test.js'],coverage:{provider:'v8',include:['quiz_app/static/*.js'],thresholds:{lines:100,functions:100,branches:90,statements:100}}}});
