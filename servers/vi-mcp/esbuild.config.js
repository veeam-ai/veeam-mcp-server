import * as esbuild from 'esbuild';

const entryPoint = process.argv.includes('--debug') ? 'src/debug.ts' : 'src/index.ts';

await esbuild.build({
    entryPoints: [entryPoint],
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
    sourcesContent: true,
});
