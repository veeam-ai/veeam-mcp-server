import * as esbuild from 'esbuild';

await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle: true,
    platform: 'node',
    target: 'es2022',
    format: 'esm',
    outfile: 'build/index.js',
    external: [
        '@modelcontextprotocol/sdk',
        'axios',
        'dotenv',
        'rxjs',
        'socket.io-client',
        'uuid'
    ],
    sourcemap: true,
});
