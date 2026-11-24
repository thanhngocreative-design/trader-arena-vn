"""Artifact metadata fixtures; never market prices or portfolio results."""
import shutil,subprocess
from pathlib import Path
import pytest

def test_visibility_wait_never_selects_another_or_expired_artifact():
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    root=Path(__file__).resolve().parents[1]
    script=r'''
const assert=require('node:assert/strict');
const {waitForArtifact}=require('./.github/actions/deploy-site/wait-artifact.cjs');
(async()=>{
 const valid={id:17,name:'paper-2',expired:false,size_in_bytes:1200};
 let calls=0,waits=0;
 const result=await waitForArtifact({id:17,name:'paper-2',list:async()=>({artifacts:++calls<3?[{...valid,id:16}]:[valid]}),pause:async()=>waits++});
 assert.equal(result,valid);assert.equal(calls,3);assert.equal(waits,2);
 for(const artifact of [{...valid,id:16},{...valid,name:'paper-1'},{...valid,expired:true},{...valid,size_in_bytes:0}]){
  let attempts=0;
  await assert.rejects(waitForArtifact({id:17,name:'paper-2',attempts:2,pause:async()=>{},list:async()=>{attempts++;return {artifacts:[artifact]}}}),/refusing to publish/);
  assert.equal(attempts,2);
 }
 await assert.rejects(waitForArtifact({id:0,name:'paper',list:async()=>{throw Error('must not run')}}),/identity/);
 await assert.rejects(waitForArtifact({id:17,name:'paper',list:async()=>({})}),/Invalid artifact/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run([node,'-e',script],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
