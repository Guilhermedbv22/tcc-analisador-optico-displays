import { getStore } from '@netlify/blobs';
import { createAPI } from '../../server/api.mjs';
export default createAPI(()=>getStore({name:'iris-reports-v1',consistency:'strong'}),{adminToken:process.env.IRIS_ADMIN_TOKEN||''});
export const config={path:['/api/health','/api/reports','/api/reports/*'],
  rateLimit:{windowLimit:180,windowSize:60,aggregateBy:['ip','domain']}};
