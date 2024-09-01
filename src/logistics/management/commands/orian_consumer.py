import json
import ssl

from django.conf import settings
from django.core.management.base import BaseCommand
import pika

from logistics.models import (
    LogisticsCenterEnum,
    LogisticsCenterMessage,
    LogisticsCenterMessageTypeEnum,
)
from logistics.tasks import process_logistics_center_message


class Command(BaseCommand):
    help = 'Runs the Orian consumer for the given queue'

    def handle(self, *args, **options):
        self.stdout.write('Consumer initializing...')

        # create a non-verifying ssl context since orian certificates are
        # self-signed
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # prepare connection parameters
        connection_credentials = pika.PlainCredentials(
            settings.ORIAN_RABBITMQ_USER, settings.ORIAN_RABBITMQ_PASSWORD
        )
        connection_parameters = pika.ConnectionParameters(
            host=settings.ORIAN_RABBITMQ_HOST,
            port=settings.ORIAN_RABBITMQ_PORT,
            virtual_host=settings.ORIAN_RABBITMQ_VIRTUAL_HOST,
            credentials=connection_credentials,
            ssl_options=pika.SSLOptions(context=ssl_context),
        )

        connection = pika.SelectConnection(
            connection_parameters,
            on_open_callback=self.handle_connection_open,
            on_open_error_callback=self.handle_connection_open_error,
            on_close_callback=self.handle_connection_close,
        )

        try:
            connection.ioloop.start()
        except KeyboardInterrupt:
            connection.close()
            connection.ioloop.stop()

    def handle_connection_open(self, connection):
        self.stdout.write('Connected to RabbitMQ')

        connection.channel(on_open_callback=self.handle_channel_open)

    def handle_connection_open_error(self, connection, err):
        self.stderr.write(f'RabbitMQ connection open failure: {str(err)}')
        connection.ioloop.stop()

    def handle_connection_close(self, connection, reason):
        self.stderr.write(f'RabbitMQ connection closed: {str(reason)}')
        connection.ioloop.stop()

    def handle_channel_open(self, channel):
        # make sure not to auto delete or claim exclusivity, only check that
        # the queue exists
        channel.queue_declare(
            queue='CloseeReceipt_NKS',
            passive=True,
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        channel.queue_declare(
            queue='OrderStatusChange_NKS',
            passive=True,
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        channel.queue_declare(
            queue='ShipOrder_NKS',
            passive=True,
            durable=True,
            exclusive=False,
            auto_delete=False,
        )

        channel.basic_consume(
            queue='CloseeReceipt_NKS',
            auto_ack=False,
            on_message_callback=self.handle_consumed_closee_receipt_message,
        )
        channel.basic_consume(
            queue='OrderStatusChange_NKS',
            auto_ack=False,
            on_message_callback=self.handle_consumed_order_status_change_message,
        )
        channel.basic_consume(
            queue='ShipOrder_NKS',
            auto_ack=False,
            on_message_callback=self.handle_consumed_ship_order_message,
        )

        channel.add_on_close_callback(self.handle_channel_close)

        self.stdout.write('Waiting for messages. To exit press CTRL+C')

    def handle_channel_close(self, channel, reason):
        self.stderr.write(f'RabbitMQ channel closed: {str(reason)}')
        channel.connection.ioloop.stop()

    def handle_consumed_closee_receipt_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ):
        self.stdout.write('Got message, parsing...')

        try:
            # parse body
            body_json = json.loads(body)
            receipt_number = body_json['DATACOLLECTION']['DATA']['RECEIPT']
            self.stdout.write(f'Message receipt number: "{receipt_number}"')

            # save raw message to database
            message = LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.INBOUND_RECEIPT.name,
                raw_body=body.decode('utf-8'),
            )

            # schedule async task to process the message
            process_logistics_center_message.apply_async((message.pk,))

            # we have handled the message and can ack it since it is in our db
            # and can process it whenever we like
            channel.basic_ack(delivery_tag=method.delivery_tag)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Message receipt number "{receipt_number}" handled!'
                )
            )
        except Exception as ex:
            self.stderr.write(
                f'Failed to handle message with error "{str(ex)})" and body "{body}"'
            )

    def handle_consumed_order_status_change_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ):
        self.stdout.write('Got message, parsing...')

        try:
            # parse body
            body_json = json.loads(body)
            order_id = body_json['DATACOLLECTION']['DATA']['ORDERID']
            self.stdout.write(f'Message order id: "{order_id}"')

            # save raw message to database
            message = LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.ORDER_STATUS_CHANGE.name,
                raw_body=body.decode('utf-8'),
            )

            # schedule async task to process the message
            process_logistics_center_message.apply_async((message.pk,))

            # we have handled the message and can ack it since it is in our db
            # and can process it whenever we like
            channel.basic_ack(delivery_tag=method.delivery_tag)

            self.stdout.write(
                self.style.SUCCESS(f'Message order_id "{order_id}" handled!')
            )
        except Exception as ex:
            self.stderr.write(
                f'Failed to handle message with error "{str(ex)})" and body "{body}"'
            )

    def handle_consumed_ship_order_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ):
        self.stdout.write('Got message, parsing...')

        try:
            # parse body
            body_json = json.loads(body)
            order_id = body_json['DATACOLLECTION']['DATA']['ORDERID']
            self.stdout.write(f'Message order id: "{order_id}"')

            # save raw message to database
            message = LogisticsCenterMessage.objects.create(
                center=LogisticsCenterEnum.ORIAN.name,
                message_type=LogisticsCenterMessageTypeEnum.SHIP_ORDER.name,
                raw_body=body.decode('utf-8'),
            )

            # schedule async task to process the message
            process_logistics_center_message.apply_async((message.pk,))

            # we have handled the message and can ack it since it is in our db
            # and can process it whenever we like
            channel.basic_ack(delivery_tag=method.delivery_tag)

            self.stdout.write(
                self.style.SUCCESS(f'Message oder id "{order_id}" handled!')
            )
        except Exception as ex:
            self.stderr.write(
                f'Failed to handle message with error "{str(ex)})" and body "{body}"'
            )
