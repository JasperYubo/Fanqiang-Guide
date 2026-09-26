const jsonBody = schema => ({required:true,content:{'application/json':{schema}}});
const jsonResponse = description => ({description,content:{'application/json':{schema:{type:'object'}}}});
const responses = {200:jsonResponse('请求完成'),400:jsonResponse('输入格式有误'),401:jsonResponse('当前对话不存在或已过期'),403:jsonResponse('需要从本站同源网页发起请求'),409:jsonResponse('当前任务未完成或阶段不匹配'),429:jsonResponse('请求较多，请稍后重试'),503:jsonResponse('服务暂不可用')};
const instructions = `::ILANG::v5.0\n[TYPE:reference][SCOPE:fanqiang_public_chat][LANG:zh]\n::MODULE{CHAT_CONTRACT}\n  [MUST] 提问顺序由程序控制：确认用户可用的 AI、设备和需求，再交付 I-Lang 工程书；不得用 artifact 模式跳过已知信息确认。\n  [MUST] 本次咨询解决、工程书交付和用户自己的 AI 执行成功是不同状态；只保留明确反馈，不将未反馈视为成功。\n  [MUST] 公开许可为独立可选项，默认 false；回答和下载不依赖公开许可。\n  [MUST] 对话与私有文件保留七天，接口不缓存；只读当前浏览器的私有会话，不要求访客提供密钥、密码或私人订阅。\n::ILANG::COMPLETE::`;
export const CHAT_OPENAPI = {
  openapi:'3.1.0',info:{title:'Fanqiang Guide 同源网页问答',version:'1.2.0',description:instructions},
  servers:[{url:'https://fanqiang.guide'}],
  components:{securitySchemes:{chatSession:{type:'apiKey',in:'cookie',name:'__Secure-fg_chat'}}},
  paths:{
    '/api/chat/health':{get:{operationId:'chatHealth',security:[],responses:{200:jsonResponse('问答接口运行状态与公开契约地址')}}},
    '/api/chat/session':{post:{operationId:'chatSession',security:[],description:'从同源网页建立或恢复私有对话；响应通过 HttpOnly Cookie 绑定当前浏览器，并返回当前提问阶段与结果状态。',requestBody:jsonBody({type:'object',additionalProperties:false}),responses}},
    '/api/chat/reset':{post:{operationId:'chatReset',security:[{chatSession:[]}],description:'清空当前私有对话和下载文件，取消待处理任务；已公开案例进入撤回处理。',requestBody:jsonBody({type:'object',additionalProperties:false}),responses}},
    '/api/chat/message':{post:{operationId:'chatMessage',security:[{chatSession:[]}],description:'同源网页提交问题，接收 SSE flow/status/delta/sources/artifact/done 或 error；按 flow 提示继续，不猜测成功状态。',requestBody:jsonBody({type:'object',required:['message','requestId'],properties:{message:{type:'string',minLength:1,maxLength:1500},requestId:{type:'string',minLength:16,maxLength:80},mode:{type:'string',enum:['answer','artifact'],default:'answer'},context:{type:'string',maxLength:1500}}}),responses:{...responses,200:{description:'SSE 提问阶段、回答与私有交付物',content:{'text/event-stream':{schema:{type:'string'}}}}}}},
    '/api/chat/review':{
      get:{operationId:'chatReviewStatus',security:[{chatSession:[]}],description:'读取本次结果确认及 AI 答案检查；公开案例需单独许可。',responses},
      post:{operationId:'chatConfirmResult',security:[{chatSession:[]}],description:'工程书交付后，分别确认咨询结果、执行反馈和可选匿名公开许可。needs_more 会继续原对话；重复 requestId 不重复创建任务。',requestBody:jsonBody({type:'object',required:['requestId','resolution','execution','allowPublish'],properties:{requestId:{type:'string',minLength:16,maxLength:80},resolution:{type:'string',enum:['resolved','needs_more','unconfirmed']},execution:{type:'string',enum:['not_reported','succeeded','failed']},allowPublish:{type:'boolean',default:false}}}),responses}},
    '/api/chat/artifacts/{id}':{get:{operationId:'chatDownloadBook',security:[{chatSession:[]}],description:'仅当前对话可读取的 I-Lang 工程书；过期或其他会话返回 404。',parameters:[{name:'id',in:'path',required:true,schema:{type:'string',format:'uuid'}}],responses:{200:{description:'私有 I-Lang 工程书文件',content:{'text/plain':{schema:{type:'string'}}}},404:jsonResponse('文件不存在或已过期')}}},
  },
};
