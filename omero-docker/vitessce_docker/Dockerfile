FROM node:current-bullseye

# set our node environment, either development or production
# defaults to production, compose overrides this to development on build and run
ARG NODE_ENV=production
ENV NODE_ENV $NODE_ENV

# default to port 3000 for node
EXPOSE 3000

RUN npm i npm@latest -g

USER node

WORKDIR /webapp

COPY --chown=node:node ./webapp/package*.json ./
RUN npm ci && npm cache clean --force
COPY --chown=node:node webapp/src ./

# Starting our application
CMD npm start
