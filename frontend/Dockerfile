FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json /app/
RUN npm ci
COPY . /app
ARG VITE_PRODUCT_API_BASE
ARG VITE_CART_API_BASE
ARG VITE_ORDER_API_BASE
ENV VITE_PRODUCT_API_BASE=$VITE_PRODUCT_API_BASE \
    VITE_CART_API_BASE=$VITE_CART_API_BASE \
    VITE_ORDER_API_BASE=$VITE_ORDER_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

