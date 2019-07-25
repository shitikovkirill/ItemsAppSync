from aws_cdk import core
from aws_cdk.aws_appsync import (
    CfnGraphQLApi, CfnApiKey, CfnGraphQLSchema, CfnDataSource, CfnResolver
)
from aws_cdk.aws_dynamodb import (
    Table, Attribute, AttributeType, StreamViewType, BillingMode,
)
from aws_cdk.aws_iam import (
    Role, ServicePrincipal, ManagedPolicy
)


class AppSynckStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        table_name = 'items'

        items_graphql_api = CfnGraphQLApi(
            self,
            'ItemsApi',
            name='items-api',
            authentication_type='API_KEY'
        )

        CfnApiKey(
            self,
            'ItemsApiKey',
            api_id=items_graphql_api.attr_api_id
        )

        api_schema = CfnGraphQLSchema(
            self,
            'ItemsSchema',
            api_id=items_graphql_api.attr_api_id,
            definition="""
                type {table_name} {{
                    {table_name}Id: ID!
                    name: String
                }}
                type Paginated{table_name} {{
                    items: [{table_name}!]!
                    nextToken: String
                }}
                type Query {{
                    all(limit: Int, nextToken: String): Paginated{table_name}!
                    getOne({table_name}Id: ID!): {table_name}
                }}
                type Mutation {{
                    save(name: String!): {table_name}
                    delete({table_name}Id: ID!): {table_name}
                }}
                type Schema {{
                    query: Query
                    mutation: Mutation
                }}
                """.format(table_name=table_name)
        )

        items_table = Table(
            self,
            'ItemsTable',
            table_name=table_name,
            partition_key=Attribute(
                name="{}Id".format(table_name),
                type=AttributeType.STRING,
            ),
            billing_mode=BillingMode.PAY_PER_REQUEST,
            stream=StreamViewType.NEW_IMAGE
        )

        items_table_role = Role(
            self,
            'ItemsDynamoDBRole',
            assumed_by=ServicePrincipal('appsync.amazonaws.com')
        )

        items_table_role.add_managed_policy(
            ManagedPolicy.from_aws_managed_policy_name('AmazonDynamoDBFullAccess')
        )

        data_source = CfnDataSource(
            self,
            'ItemsDataSource',
            api_id=items_graphql_api.attr_api_id,
            name='ItemsDynamoDataSource',
            type='AMAZON_DYNAMODB',
            dynamo_db_config=CfnDataSource.DynamoDBConfigProperty(
                table_name=items_table.table_name,
                aws_region=self.region
            ),
            service_role_arn=items_table_role.role_arn
        )

        get_one_resolver = CfnResolver(
            self,
            'GetOneQueryResolver',
            api_id=items_graphql_api.attr_api_id,
            type_name='Query',
            field_name='getOne',
            data_source_name=data_source.name,
            request_mapping_template="""{{
                "version": "2017-02-28",
                "operation": "GetItem",
                "key": {{
                    "{table_name}Id": $util.dynamodb.toDynamoDBJson($ctx.args.{table_name}Id)
                }}
            }}""".format(table_name=table_name),
            response_mapping_template="$util.toJson($ctx.result)"
        )
        get_one_resolver.add_depends_on(api_schema)

        get_all_resolver = CfnResolver(
            self,
            'GetAllQueryResolver',
            api_id=items_graphql_api.attr_api_id,
            type_name='Query',
            field_name='all',
            data_source_name=data_source.name,
            request_mapping_template="""
            {
                "version": "2017-02-28",
                "operation": "Scan",
                "limit": $util.defaultIfNull($ctx.args.limit, 20),
                "nextToken": $util.toJson($util.defaultIfNullOrEmpty($ctx.args.nextToken, null))
            }""",
            response_mapping_template="$util.toJson($ctx.result)"
        )
        get_all_resolver.add_depends_on(api_schema)

        save_resolver = CfnResolver(
            self,
            'SaveMutationResolver',
            api_id=items_graphql_api.attr_api_id,
            type_name='Mutation',
            field_name='save',
            data_source_name=data_source.name,
            request_mapping_template="""{{
                "version": "2017-02-28",
                "operation": "PutItem",
                "key": {{
                    "{table_name}Id": {{"S": "$util.autoId()"}}
                }},
                "attributeValues": {{
                    "name": $util.dynamodb.toDynamoDBJson($ctx.args.name)
                }}
            }}""".format(table_name=table_name),
            response_mapping_template="$util.toJson($ctx.result)"
        )
        save_resolver.add_depends_on(api_schema)

        delete_resolver = CfnResolver(
            self,
            'DeleteMutationResolver',
            api_id= items_graphql_api.attr_api_id,
            type_name='Mutation',
            field_name='delete',
            data_source_name=data_source.name,
            request_mapping_template="""{{
                "version": "2017-02-28",
                "operation": "DeleteItem",
                "key": {{
                    "{table_name}Id": $util.dynamodb.toDynamoDBJson($ctx.args.{table_name}Id)
                }}
            }}""".format(table_name=table_name),
            response_mapping_template="$util.toJson($ctx.result)"
        )
        delete_resolver.add_depends_on(api_schema)
