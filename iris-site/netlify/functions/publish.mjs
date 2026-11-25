import { getStore } from '@netlify/blobs';
import { createAPI } from '../../server/api.mjs';
export default createAPI(()=>getStore({name:'iris-reports-v1',consistency:'strong'}));
export const config={path:'/api/publish',
  rateLimit:{windowLimit:10,windowSize:3600,aggregateBy:['ip','domain']}};
