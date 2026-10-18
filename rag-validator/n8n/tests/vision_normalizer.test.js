const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const main=JSON.parse(fs.readFileSync(path.join(__dirname,'..','solvey_main.json'),'utf8'));
const js=main.nodes.find(n=>n.name==='Normalize & Parse Vision').parameters.jsCode;
const routeJs=main.nodes.find(n=>n.name==='Route Safety & Confidence').parameters.jsCode;
function run(input){return new Function('$input',js)({first:()=>({json:input})})[0].json;}
function route(input){return new Function('$input',routeJs)({first:()=>({json:input})})[0].json;}
const real="Application or operating system: Not visible.\n\nError message(s): \n- \"Page has expired\"\n- \"Click here\" (appears twice)\n\nError codes: None\n\nState of screen: A webpage displaying an error indicating the page has expired, with two identical hyperlinks labeled “Click here”. The word “skrulls” is visible in the top-left corner.";
test('parses the supplied real Qwen output',()=>{
 const out=run({request_id:'r1',title:'VPN',description:'Cannot sign in',vision_description:real,vision_model:'qwen3-vl:4b-instruct-q4_K_M',category:'Network & VPN',subcategory:'VPN authentication failure',confidence:0.82});
 assert.equal(out.vision.application,null);
 assert.equal(out.vision.error_text,'Page has expired; Click here (appears twice)');
 assert.equal(out.vision.error_code,null);
 assert.match(out.vision.observations[0],/skrulls/);
 assert.equal(out.vision.usable,true);
 assert.equal(out.vision.confidence,0.8);
 assert.equal(out.classifier_hint.category,'network_vpn');
 assert.equal(out.classifier_hint.subcategory,'vpn_auth_failure');
});
test('preserves unknown parser text and maps unknown labels to other',()=>{
 const raw='Screenshot is blurry and text is unreadable';
 const out=run({description:'Please help',vision_description:raw,category:'Unknown',subcategory:'???',confidence:0.2});
 assert.equal(out.vision.usable,false);assert.equal(out.vision_raw_text,raw);
 assert.equal(out.vision.error_text,raw);assert.equal(out.vision.confidence,0.5);
 assert.equal(out.classifier_hint.category,'other');
});
test('text-only requests retain null vision',()=>{
 assert.equal(run({description:'The app will not open',vision_description:''}).vision,null);
});
test('security keywords override a false model flag and force a critical ticket',()=>{
 const normalized=run({title:'Account issue',description:'My work account was hacked',vision_description:''});
 const result=route({...normalized,triage:{category:'auth_access',subcategory:'mfa_failure',confidence:0.9,language:'en',is_sensitive:false,needs_clarification:false,search_query:'account login'}});
 assert.equal(result.triage.is_sensitive,true);
 assert.equal(result.triage.urgency,'critical');
 assert.equal(result.route_action,'ticket');
});
test('unreadable screenshot takes the clarification path',()=>{
 const normalized=run({title:'Blurry screenshot',description:'Please help me read this error',vision_description:'The screenshot text is unreadable'});
 const result=route({...normalized,triage:{category:'network_vpn',subcategory:'vpn_auth_failure',confidence:0.9,language:'en',is_sensitive:false,needs_clarification:false,search_query:'VPN error'}});
 assert.equal(result.triage.needs_clarification,true);
 assert.equal(result.route_action,'clarify');
});
