// Read-only live check: deliberately cannot enable dispatch or read credentials.
import {check} from './worker.mjs';
console.log(JSON.stringify(await check({DRY_RUN: 'true'}), null, 2));
